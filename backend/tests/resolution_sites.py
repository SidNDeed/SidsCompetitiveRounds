"""The resolution-site census of ruling REHEARSAL-FOUR-R5 fix 1 (shared by
the bound test and by the survey): in each function span of a walker, the
sites that decide what a walked identifier denotes.

The walkers are every function of closed_walk.py and every function of the
a1 and gate test modules that is not a test (a `test_*` function and the
definitions nested in it are oracles over fixed code and test scaffolding,
not walks).

A KEY expression carries a walked identifier: it reads `.id` off a tree
node, or is a name the span bound (assigned, looped, unpacked, walrus) from
an expression whose value can carry one (a comparison's operands and a
comprehension's conditions decide which values, they are not the value). A TEXT expression is a call of `unparse`, or a name the
span bound from one. A resolution site is:
  getattr(<x>, K, ...)   K a KEY expression or reads `.attr`;
  <x>[K] / <x>.get(K)    K a KEY expression (a name-table lookup);
  a comparison           ==, !=, in, not in, with a KEY operand, or with a
                         TEXT operand against anything but a string literal
                         that is not a dotted identifier (a callee's or a
                         constant's spelling compared; a whole statement's
                         text compared with a fixed non-identifier text is a
                         shape assertion, not a resolution);
  import_module(...)     an import by name.
Every site of a span inside class Bindings goes through the resolver.
Outside it, a call is the resolver's own (its answer is not a KEY) in ONE
frozen form only (round 8, ruling REHEARSAL-FOUR-R7-A1, M7): a method
class Bindings defines, called on the attribute `b` of a plain name,
`<name>.b.<method>(...)`. Round 9 (ruling REHEARSAL-R8-A1, G2) binds the
form's receiver, which round 8 left free (finding resolution_sites:65:
`return b.b.named(n.id) == 'db'`, with `b.b` an ordinary object, passed
the grammar and counted no site): the plain name is a FROZEN receiver
(RESOLVER_RECEIVERS, keyed by the module-level class whose `__init__`
stores the resolver: `self` in a method of class Visitor, closed_walk's,
and `w` in a module holding class _Walk, the gate walks'), bound in the
span only as that receiver is (the method's first parameter; a parameter
of a module-level function, or a store from `_Walk(...)`), and the chain
behind it is checked
(receiver_problems: the module's one store to `.b` is its class's
`__init__` storing a Bindings; every call of a gate function taking `w`
passes `w` or `_Walk(...)`). Any other receiver makes the call an
ordinary expression, its value read for KEY and TEXT: `b.named(...)` on
a plain name, `b.b.named(...)` on a name that is not the frozen
receiver, the visitor's `self._check(...)` and `self._resolve(...)`,
`Bindings(...).<method>(...)`. The resolver call's ARGUMENTS are read
like any other expression of the span (round 7, finding
resolution_sites:132: a decision evaluated inside a resolver call's
argument contributed no site).

Round 9 also binds the census's own forms (G3, form_problems): the
spellings a site is recognised by (getattr, hasattr, __import__) are
used only as the callee of a call and never bound, and the methods it is
recognised by (`.get`, `.unparse`, `.import_module`) only called, so no
alias carries a site past the count; a lambda is part of the span that
holds it; a walker span that names a `test_*` function of its module
refuses (a test function is outside the census only because no walk
reaches it).

Round 10 (ruling REHEARSAL-R9-A1 (C)) binds the receiver by IDENTITY, not
by presence (finding resolution_sites:202: selecting `policy` instead of
`bindings` in Visitor.__init__ kept a `Bindings(...)` call in the unused
alternative, and the check passed). The receiver's complete store
statement is frozen (RECEIVER_STORES: shape_grammar.header_digest of the
whole `self.b = ...` statement, every alternative of its value included);
every alternative of the value is a frozen source (a construction of the
resolver class through its one provider binding in the module, or a
parameter of `__init__`); and the parameter's own sources, across the
census modules, are a frozen chain (receiver_sources, RECEIVER_SOURCES):
every call that constructs the class, every function that hands the value
on, every local and every return it passes through, each ending in a
resolver construction, the None default, or a frozen receiver's `.b`. Any
other value refuses.
Round 10 also bounds comparison ARITY (finding resolution_sites:431:
`name is not 'db' is not None` matched the admitted Compare shape, whose
lists are sets of classes, and the None exemption suppressed the whole
chain): a chained comparison in a walker span is a form problem, and the
None exemption covers exactly one comparison, `<x> is None` or
`<x> is not None`, with the single comparator the None constant.

Round 7 (ruling REHEARSAL-FOUR-R6 (1)(b)): the census is DEFAULT-DENY.
Before any site is counted, every node of every walker span is checked
against WALKER_SHAPES (grammar_shapes_a1.py), the frozen shapes of the
walker code itself (shape_grammar.shape); the walker code holds no
annotated assignment, so one refuses (finding resolution_sites:145:
`name: str = node.id` was not followed). `grammar_refusals` lists every
node outside it.
"""
import ast

import shape_grammar as _sg

RESOLVER_CLASS = "Bindings"
RESOLVER_METHODS = set()
_PRUNED = {}

# The frozen resolver receivers (round 9, ruling REHEARSAL-R8-A1, G2): the
# module-level class whose `__init__` holds the module's one store to `.b`
# (receiver_problems), and the receiver spelling it admits: `self` in that
# class's own methods; `w` in the module's module-level functions. A module
# holding neither class has no resolver form at all.
RESOLVER_RECEIVERS = {
    "Visitor": "self",
    "_Walk": "w",
}
# The receiver the span being counted admits (None: no resolver form).
_RECEIVER = {"spelling": None}
# The spellings and methods a site is recognised by (form_problems).
SITE_NAMES = frozenset({"getattr", "hasattr", "__import__"})
SITE_METHODS = frozenset({"get", "unparse", "import_module"})
# The module that defines the resolver class (round 10): a resolver
# construction outside it is `<X>.Bindings(...)` with X bound once, at the
# top level, by `import closed_walk as X`.
RESOLVER_HOME = "closed_walk"
# The frozen complete store statement of each receiver class (round 10,
# finding resolution_sites:202): shape_grammar.header_digest of the whole
# `self.b = ...` statement of its `__init__`, taken once at 0b317394.
RECEIVER_STORES = {
    "Visitor": "deb50a21d5de8fad",
    "_Walk": "36214a5241768ebf",
}
# The frozen value chain of the receivers' parameter sources (round 10,
# receiver_sources over closed_walk, the a1 file and the gate file), taken
# once at 0b317394 and never regenerated: (kind, module, qualname, detail),
# detail the header digest of the statement holding the hop or end (a
# parameter's name; a function's number of returns). Visitor's `bindings`
# reaches it from closed_walk.def_effects's own construction, from
# closed_walk.expr_effects's parameter (the a1 file's wrapper's parameter,
# given the a1 handler's `b = _handler_bindings(...)`, whose one return is a
# construction) and from the gate's `_effects` as `w.b`.
RECEIVER_SOURCES = frozenset({
    ("construction", "closed_walk", "def_effects", "2c400d7bf7ef4eb1"),
    ("construction", "test_a1_identity_formation", "_handler_bindings",
     "0d4a073ae0f9221c"),
    ("local", "closed_walk", "def_effects", "2c400d7bf7ef4eb1"),
    ("local", "test_a1_identity_formation", "formation_loop_exits",
     "119f72d4d9c5532c"),
    ("local", "test_a1_identity_formation", "formation_loop_exits.effects_of",
     "119f72d4d9c5532c"),
    ("parameter", "closed_walk", "Visitor.__init__", "bindings"),
    ("parameter", "closed_walk", "expr_effects", "bindings"),
    ("parameter", "test_a1_identity_formation", "expr_effects", "bindings"),
    ("receiver", "test_match_hold_admission_gate_pg", "_effects",
     "988d63c501bd7bf9"),
    ("returns", "test_a1_identity_formation", "_handler_bindings", 1),
})


def resolver_methods(tree):
    """The method names class Bindings defines in module tree."""
    out = set()
    for c in ast.walk(tree):
        if isinstance(c, ast.ClassDef) and c.name == RESOLVER_CLASS:
            out |= {d.name for d in c.body
                    if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return out


def _resolver_call(x):
    """Whether x is a resolver call in the one frozen resolver form,
    `<name>.b.<method>(...)` with <method> one class Bindings defines and
    <name> the receiver the span admits (round 9: the frozen receiver of
    the module, span_receiver)."""
    if not isinstance(x, ast.Call):
        return False
    f = x.func
    return (isinstance(f, ast.Attribute) and f.attr in RESOLVER_METHODS
            and isinstance(f.value, ast.Attribute) and f.value.attr == "b"
            and isinstance(f.value.value, ast.Name)
            and _RECEIVER["spelling"] is not None
            and f.value.value.id == _RECEIVER["spelling"])


def _parents(root):
    """{id(node): parent} under root."""
    out = {}
    for p in ast.walk(root):
        for c in ast.iter_child_nodes(p):
            out[id(c)] = p
    return out


def _params(d):
    a = d.args
    return a.posonlyargs + a.args + a.kwonlyargs + [
        x for x in (a.vararg, a.kwarg) if x is not None]


def module_receivers(tree):
    """{class: receiver spelling} of the frozen receivers whose class
    module tree defines at module level."""
    return {c.name: RESOLVER_RECEIVERS[c.name] for c in tree.body
            if isinstance(c, ast.ClassDef) and c.name in RESOLVER_RECEIVERS}


def span_receiver(receivers, qualname, d):
    """The receiver spelling outermost span d (qualname) admits for the
    resolver form, or None; `receivers` the module's (module_receivers).
    `self`: in a method of its class whose first parameter it is, bound
    nowhere else in the span. `w`: a module-level function's span in which
    every binding of `w` is a parameter of the function itself or a
    single-name store from `<its class>(...)`."""
    for cls, spelling in sorted(receivers.items()):
        if spelling == "self" and qualname == f"{cls}.{d.name}":
            return _self_receiver(d, spelling)
        if spelling != "self" and "." not in qualname:
            return _param_receiver(d, spelling, cls)
    return None


def _self_receiver(d, spelling):
    binds = [b for b in _sg.bindings(d) if b[1] == spelling]
    own = d.args.posonlyargs + d.args.args
    ok = (own and own[0].arg == spelling and len(binds) == 1
          and binds[0][2] == "parameter")
    return spelling if ok else None


def _param_receiver(d, spelling, cls):
    binds = [b for b in _sg.bindings(d) if b[1] == spelling]
    par = _parents(d)
    good = 0
    for a in _params(d):
        good += a.arg == spelling
    for n in ast.walk(d):
        if (isinstance(n, ast.Name) and n.id == spelling
                and isinstance(n.ctx, ast.Store)):
            p = par.get(id(n))
            if (isinstance(p, ast.Assign) and p.targets == [n]
                    and isinstance(p.value, ast.Call)
                    and isinstance(p.value.func, ast.Name)
                    and p.value.func.id == cls):
                good += 1
    return spelling if good == len(binds) and binds else None


def receiver_problems(tree):
    """[(line, sentence)] of the chain behind each frozen receiver module
    tree holds (round 9, G2): the module's one store to an attribute `b` is
    `self.b = <a value calling Bindings>` in its class's `__init__`; with
    the parameter route (`w`), every call of a module-level function that
    takes `w` passes the name `w` or `<class>(...)` to it, and no such
    function is named other than as a callee."""
    out = []
    for cls, spelling in sorted(module_receivers(tree).items()):
        out.extend(_chain_problems(tree, cls, spelling))
    return out


def _chain_problems(tree, cls, spelling):
    out = []
    par = _parents(tree)
    # round 10 (the sweep of finding resolution_sites:202's class): the
    # receiver class is the module's by identity, its one binding the
    # class statement, so `_Walk(...)` (the `w` route's store, its callers'
    # argument) and `self` in its methods are THE class's
    st = _top_binder(tree, cls)
    if not (isinstance(st, ast.ClassDef) and st.name == cls):
        out.append((getattr(st, "lineno", 0), f"the receiver class {cls} is not "
                                              "bound once, by its class statement"))
    stores = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute)
              and n.attr == "b" and not isinstance(n.ctx, ast.Load)]
    init = [d for c in tree.body if isinstance(c, ast.ClassDef) and c.name == cls
            for d in c.body if isinstance(d, ast.FunctionDef)
            and d.name == "__init__"]
    good = []
    for n in stores:
        st = par.get(id(n))
        if not (init and isinstance(n.value, ast.Name) and n.value.id == "self"
                and isinstance(st, ast.Assign) and len(st.targets) == 1
                and st.targets[0] is n
                and any(n is x for x in ast.walk(init[0]))):
            continue
        # round 10: the complete statement, then every alternative of its
        # value (finding resolution_sites:202: a Bindings call anywhere in
        # the value was enough)
        if _sg.header_digest(st) != RECEIVER_STORES.get(cls):
            out.append((st.lineno, f"{cls}.__init__'s store to `.b` is not "
                                   "its frozen statement"))
            continue
        bad = [why for alt in _alternatives(st.value)
               for why in (_store_source(tree, init[0], alt),) if why]
        out.extend((st.lineno, why) for why in bad)
        if not bad:
            good.append(n)
    if len(stores) != 1 or len(good) != 1:
        out.append((stores[0].lineno if stores else 0,
                    f"the stores to `.b` are not exactly {cls}.__init__'s "
                    f"one store of a {RESOLVER_CLASS}: {len(stores)} stores"))
    if spelling == "self":
        return out
    fns = {d.name: d for d in tree.body
           if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef))}
    takes = {n for n, d in fns.items() if any(a.arg == spelling for a in _params(d))}
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id in takes:
            p = par.get(id(n))
            if not (isinstance(p, ast.Call) and p.func is n):
                out.append((n.lineno, f"{n.id}, which takes `{spelling}`, is "
                                      "named other than as a callee"))
                continue
            d = fns[n.id]
            pos = [a.arg for a in d.args.posonlyargs + d.args.args]
            arg = None
            if spelling in pos and pos.index(spelling) < len(p.args):
                arg = p.args[pos.index(spelling)]
            for k in p.keywords:
                if k.arg == spelling or k.arg is None:
                    arg = k.value if k.arg == spelling else k
            if any(isinstance(a, ast.Starred) for a in p.args):
                arg = None
            if not ((isinstance(arg, ast.Name) and arg.id == spelling)
                    or (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name)
                        and arg.func.id == cls)):
                out.append((n.lineno, f"a call of {n.id} passes "
                                      f"{ast.unparse(arg) if isinstance(arg, ast.AST) else arg} "
                                      f"as `{spelling}`"))
    return out


def _alternatives(e):
    """Every value expression `e` can evaluate to, through conditional
    expressions (round 10)."""
    if isinstance(e, ast.IfExp):
        return _alternatives(e.body) + _alternatives(e.orelse)
    return [e]


def _top_binder(tree, name):
    """The one top-level statement of module tree that binds `name`, when
    the module binds it exactly once anywhere; None otherwise."""
    if sum(1 for _l, s, _h in _sg.bindings(tree) if s == name) != 1:
        return None
    hits = [st for st in tree.body
            if any(s == name for _l, s, _h in _sg.bindings(st))]
    return hits[0] if len(hits) == 1 else None


def _resolver_construction(tree, e):
    """Whether `e` constructs the resolver class through its one provider
    binding in module tree: `Bindings(...)` where the module binds the name
    once, by its top-level class statement; or `<X>.Bindings(...)` where
    the module binds X once, by a top-level `import closed_walk as X`."""
    if not isinstance(e, ast.Call):
        return False
    f = e.func
    if isinstance(f, ast.Name) and f.id == RESOLVER_CLASS:
        st = _top_binder(tree, f.id)
        return isinstance(st, ast.ClassDef) and st.name == RESOLVER_CLASS
    if (isinstance(f, ast.Attribute) and f.attr == RESOLVER_CLASS
            and isinstance(f.value, ast.Name)):
        st = _top_binder(tree, f.value.id)
        return (isinstance(st, ast.Import) and len(st.names) == 1
                and st.names[0].name == RESOLVER_HOME
                and st.names[0].asname == f.value.id)
    return False


def _store_source(tree, init, alt):
    """None when the alternative `alt` of a receiver store in `init` is a
    frozen source (a resolver construction, or a parameter of `init` bound
    there once, defaulting to None if it has a default); the sentence
    otherwise."""
    if _resolver_construction(tree, alt):
        return None
    if isinstance(alt, ast.Name):
        binds = [h for _l, s, h in _sg.bindings(init) if s == alt.id]
        a = init.args
        pos = a.posonlyargs + a.args
        names = [x.arg for x in pos]
        defaults = dict(zip(names[len(names) - len(a.defaults):], a.defaults))
        defaults.update({x.arg: d for x, d in zip(a.kwonlyargs, a.kw_defaults)
                         if d is not None})
        dflt = defaults.get(alt.id)
        if binds == ["parameter"] and (dflt is None or (
                isinstance(dflt, ast.Constant) and dflt.value is None)):
            return None
    return (f"the receiver's value alternative `{ast.unparse(alt)}` is no "
            "frozen source")


def _def_info(tree):
    """{id(node): (qualname, chain)} for every node of module tree: the
    qualified name and the enclosing function definitions (outermost
    first) of the innermost definition holding it ('<module>', [] at the
    top level)."""
    out = {}

    def go(node, qual, chain):
        for c in ast.iter_child_nodes(node):
            out[id(c)] = (qual, chain)
            if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = f"{qual}.{c.name}" if qual != "<module>" else c.name
                go(c, q, chain if isinstance(c, ast.ClassDef) else chain + [c])
            else:
                go(c, qual, chain)
    go(tree, "<module>", [])
    return out


def _own_binds(d, name):
    """The bindings of `name` in definition d's own span: 'parameter' for
    each parameter, else the binding node (a store outside nested
    definitions, a nested definition's name, an import alias, an except
    name, a global or nonlocal declaration)."""
    out = ["parameter" for a in _params(d) if a.arg == name]
    todo = list(ast.iter_child_nodes(d))
    while todo:
        n = todo.pop()
        if isinstance(n, ast.arguments):
            continue
        if isinstance(n, ast.Name) and n.id == name and not isinstance(n.ctx, ast.Load):
            out.append(n)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if n.name == name:
                out.append(n)
            continue
        elif isinstance(n, ast.alias) and (n.asname or n.name.split(".")[0]) == name:
            out.append(n)
        elif isinstance(n, ast.ExceptHandler) and n.name == name:
            out.append(n)
        elif isinstance(n, (ast.Global, ast.Nonlocal)) and name in n.names:
            out.append(n)
        todo.extend(ast.iter_child_nodes(n))
    return out


def _call_arg(call, d, p, skip):
    """(kind, expression) of the argument `call` gives parameter p of
    definition d (`skip` leading parameters not passed, a method's self):
    ('arg', e), ('default', None), or ('unpacked', None)."""
    if any(isinstance(a, ast.Starred) for a in call.args) or any(
            k.arg is None for k in call.keywords):
        return ("unpacked", None)
    for k in call.keywords:
        if k.arg == p:
            return ("arg", k.value)
    pos = [a.arg for a in d.args.posonlyargs + d.args.args][skip:]
    if p in pos and pos.index(p) < len(call.args):
        return ("arg", call.args[pos.index(p)])
    return ("default", None)


def _callers(trees, home, name):
    """([(module, call)], [(module, line)]): every call of module-level
    `name` of module `home` (`name(...)` in home, `<X>.name(...)` in a
    module binding X once, at the top level, by `import <home> as X`), and
    every other reference to it."""
    calls, other = [], []
    for m, t in sorted(trees.items()):
        par = _parents(t)
        alias = None
        if m != home:
            for st in t.body:
                if (isinstance(st, ast.Import) and len(st.names) == 1
                        and st.names[0].name == home):
                    alias = st.names[0].asname or home
            if alias is not None and _top_binder(t, alias) is None:
                other.append((m, 0))
                alias = None
        for n in ast.walk(t):
            hit = ((m == home and isinstance(n, ast.Name) and n.id == name
                    and isinstance(n.ctx, ast.Load))
                   or (alias is not None and isinstance(n, ast.Attribute)
                       and n.attr == name and isinstance(n.value, ast.Name)
                       and n.value.id == alias))
            if not hit:
                continue
            up = par.get(id(n))
            if isinstance(up, ast.Call) and up.func is n:
                calls.append((m, up))
            else:
                other.append((m, n.lineno))
    return calls, other


def _stmt_of(par, n):
    while n is not None and not isinstance(n, ast.stmt):
        n = par.get(id(n))
    return n


def receiver_sources(trees):
    """(sources, problems) of the frozen receivers' value sources across
    the census modules `trees` ({module: tree}; round 10, ruling
    REHEARSAL-R9-A1 (C), finding resolution_sites:202). For each receiver
    class whose store takes a parameter of `__init__` (Visitor's
    `bindings`), every call constructing the class gives that parameter a
    value; each value is followed through a frozen chain only: a parameter
    of a module-level function (to every call of it), a local bound once
    by a plain assignment (to its value), a call of a module-level
    function of the same module (to each of its returns). The chain ends
    in a resolver construction (_resolver_construction), the None
    constant or an absent argument (the store's own `is not None` test
    then takes the construction), or `<w>.b` with w the frozen receiver of
    its span. `sources` is the set of every hop and end, as (kind, module,
    qualname, detail); any other form is a problem. The census test
    asserts `sources` equals RECEIVER_SOURCES. A call inside a module-level
    `test_*` function is not followed: like walker_spans, the census reads
    a test function as an oracle over fixed code, not a walk."""
    found, problems = set(), []
    info = {m: _def_info(t) for m, t in trees.items()}
    pars = {m: _parents(t) for m, t in trees.items()}
    seen = set()

    def oracle(m, call):
        chain = info[m].get(id(call), ("", []))[1]
        return bool(chain) and chain[0].name.startswith("test_") and any(
            chain[0] is d for d in trees[m].body)

    def follow(m, e, chain, depth, at):
        q = info[m].get(id(at), ("<module>", []))[0]
        st = _stmt_of(pars[m], at)
        dg = _sg.header_digest(st) if st is not None else "-"
        if depth > 40:
            problems.append((m, q, "the value chain is too long"))
            return
        if e is None or (isinstance(e, ast.Constant) and e.value is None):
            found.add(("none", m, q, dg))
            return
        if _resolver_construction(trees[m], e):
            found.add(("construction", m, q, dg))
            return
        if (isinstance(e, ast.Attribute) and e.attr == "b"
                and isinstance(e.value, ast.Name) and chain):
            top = chain[0]
            rec = span_receiver(module_receivers(trees[m]), top.name, top)
            if rec is not None and rec == e.value.id:
                found.add(("receiver", m, q, dg))
                return
        if isinstance(e, ast.Name):
            for d in reversed(chain):
                binds = _own_binds(d, e.id)
                if not binds:
                    continue
                if len(binds) != 1:
                    problems.append((m, q, f"{e.id} is bound {len(binds)} times"))
                    return
                if binds[0] == "parameter":
                    if d is not chain[0] or info[m].get(id(d), ("?",))[0] != "<module>":
                        problems.append((m, q, f"{e.id} is a parameter of a "
                                               "nested definition"))
                        return
                    key = (m, id(d), e.id)
                    if key in seen:
                        return
                    seen.add(key)
                    found.add(("parameter", m, d.name, e.id))
                    calls, other = _callers(trees, m, d.name)
                    for om, ln in other:
                        problems.append((om, d.name, f"{d.name} is named other "
                                                     f"than as a callee (line {ln})"))
                    for cm, call in calls:
                        if oracle(cm, call):
                            continue
                        kind, a = _call_arg(call, d, e.id, 0)
                        if kind == "unpacked":
                            problems.append((cm, d.name, "a call with unpacked "
                                                         "arguments"))
                            continue
                        follow(cm, a if kind == "arg" else None,
                               info[cm].get(id(call), ("", []))[1], depth + 1,
                               call)
                    return
                sst = pars[m].get(id(binds[0]))
                if (isinstance(sst, ast.Assign) and len(sst.targets) == 1
                        and sst.targets[0] is binds[0]):
                    found.add(("local", m, q, _sg.header_digest(sst)))
                    follow(m, sst.value, chain, depth + 1, sst.value)
                    return
                problems.append((m, q, f"{e.id} is bound other than by a plain "
                                       "assignment"))
                return
            problems.append((m, q, f"{e.id} is no binding of its span"))
            return
        if isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and not any(
                _own_binds(d, e.func.id) for d in chain):
            g = _top_binder(trees[m], e.func.id)
            if isinstance(g, (ast.FunctionDef, ast.AsyncFunctionDef)):
                rets = [n for n in _own(g) if isinstance(n, ast.Return)]
                found.add(("returns", m, g.name, len(rets)))
                if not rets:
                    problems.append((m, g.name, "returns no value"))
                for r in rets:
                    follow(m, r.value, [g], depth + 1, r)
                return
        problems.append((m, q, f"the value `{ast.unparse(e)}` is no frozen source"))

    for home, tree in sorted(trees.items()):
        for cls in sorted(module_receivers(tree)):
            cdef = [c for c in tree.body if isinstance(c, ast.ClassDef) and c.name == cls]
            init = [d for d in cdef[0].body if isinstance(d, ast.FunctionDef)
                    and d.name == "__init__"] if cdef else []
            if not init:
                continue
            stores = [n for n in ast.walk(init[0]) if isinstance(n, ast.Attribute)
                      and n.attr == "b" and not isinstance(n.ctx, ast.Load)]
            par = pars[home]
            for n in stores:
                st = par.get(id(n))
                alts = _alternatives(st.value) if isinstance(st, ast.Assign) else []
                for alt in alts:
                    if not isinstance(alt, ast.Name):
                        continue
                    found.add(("parameter", home, f"{cls}.__init__", alt.id))
                    calls, other = _callers(trees, home, cls)
                    for om, ln in other:
                        problems.append((om, cls, f"{cls} is named other than as "
                                                  f"a callee (line {ln})"))
                    for cm, call in calls:
                        if oracle(cm, call):
                            continue
                        kind, a = _call_arg(call, init[0], alt.id, 1)
                        if kind == "unpacked":
                            problems.append((cm, cls, "a call with unpacked "
                                                      "arguments"))
                            continue
                        follow(cm, a if kind == "arg" else None,
                               info[cm].get(id(call), ("", []))[1], 0, call)
    return found, problems


def receiver_source_problems(trees):
    """[sentence] of the receivers' value chain over the census modules
    `trees` (receiver_sources): every problem it meets, and every hop or
    end that differs from the frozen RECEIVER_SOURCES; empty when the
    chain is the frozen one."""
    found, problems = receiver_sources(trees)
    out = [f"{m}:{q}: {why}" for m, q, why in problems]
    out += [f"an unfrozen source {x!r}" for x in sorted(found - RECEIVER_SOURCES, key=repr)]
    out += [f"a frozen source missing {x!r}" for x in sorted(RECEIVER_SOURCES - found, key=repr)]
    return out


def form_problems(tree, walkers_only=True):
    """[(line, sentence)] of the census's own forms over every walker span
    of module tree (round 9, G3): a site spelling (SITE_NAMES) named other
    than as a call's callee, or bound; a site method (SITE_METHODS) read
    other than as a call's callee; a module-level `test_*` function named
    in a walker span; and the receiver chain (receiver_problems)."""
    out = list(receiver_problems(tree))
    tests = {d.name for d in tree.body if isinstance(
        d, (ast.FunctionDef, ast.AsyncFunctionDef)) and d.name.startswith("test_")}
    for _q, d in walker_spans(tree, walkers_only):
        par = _parents(d)
        for ln, s, how in _sg.bindings(d):
            if s in SITE_NAMES:
                out.append((ln, f"binds the site spelling {s} ({how})"))
        for n in ast.walk(d):
            p = par.get(id(n))
            callee = isinstance(p, ast.Call) and p.func is n
            if isinstance(n, ast.Name) and n.id in SITE_NAMES and not callee:
                out.append((n.lineno, f"the site spelling {n.id} named other "
                                      "than as a callee"))
            elif (isinstance(n, ast.Attribute) and n.attr in SITE_METHODS
                  and isinstance(n.ctx, ast.Load) and not callee):
                out.append((n.lineno, f"the site method .{n.attr} read other "
                                      "than as a callee"))
            elif (isinstance(n, ast.Name) and n.id in tests
                  and walkers_only):
                out.append((n.lineno, f"a walker names the test function {n.id}"))
            if isinstance(n, ast.Compare) and (
                    len(n.ops) != 1 or len(n.comparators) != 1):
                # round 10 (finding resolution_sites:431): a frozen Compare
                # shape lists its operators and comparators as sets of
                # classes, so a chain keeps the shape of one comparison
                out.append((n.lineno, f"a chained comparison of {len(n.ops)} "
                                      "operators"))
    return out


def _walk(e):
    """ast.walk without descending into a resolver call."""
    todo = [e]
    while todo:
        x = todo.pop()
        if _resolver_call(x):
            continue
        yield x
        todo.extend(ast.iter_child_nodes(x))


def _is_unparse(x):
    return isinstance(x, ast.Call) and (
        (isinstance(x.func, ast.Attribute) and x.func.attr == "unparse")
        or (isinstance(x.func, ast.Name) and x.func.id == "unparse"))


def _key_attr(x):
    """Whether x reads the walked identifier: `.id`, or (round 9, G3)
    `getattr(<x>, "id", ...)`, the same read spelled as a string."""
    if isinstance(x, ast.Attribute) and x.attr == "id":
        return True
    return (isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
            and x.func.id == "getattr" and len(x.args) >= 2
            and isinstance(x.args[1], ast.Constant) and x.args[1].value == "id")


def _reads(e, keyed, text=False):
    """Whether e is KEY (text False) or TEXT (text True)."""
    for x in _walk(e):
        if not text and _key_attr(x):
            return True
        if text and _is_unparse(x):
            return True
        if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load) and x.id in keyed:
            return True
    return False


def _value_walk(e):
    """The nodes of e that can reach its value: _walk without a
    comparison's operands or a comprehension's conditions (a name bound
    from `[i for i ... if x.id == "f"]` holds indices, not spellings)."""
    todo = [e]
    while todo:
        x = todo.pop()
        if _resolver_call(x) or isinstance(x, ast.Compare):
            continue
        yield x
        if isinstance(x, ast.comprehension):
            todo.extend([x.target, x.iter])
        else:
            todo.extend(ast.iter_child_nodes(x))


def _value_reads(e, keyed, text):
    for x in _value_walk(e):
        if not text and _key_attr(x):
            return True
        if text and _is_unparse(x):
            return True
        if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load) and x.id in keyed:
            return True
    return False


def _own(fn):
    """fn's nodes outside nested definitions (round 9: a lambda's nodes are
    the span's own; round 8 skipped them and no span counted them)."""
    out, todo = [], list(ast.iter_child_nodes(fn))
    while todo:
        n = todo.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        out.append(n)
        todo.extend(ast.iter_child_nodes(n))
    return out


def _pruned(fn):
    """ids of fn's resolver calls and their callee spellings (round 7: a
    resolver call's ARGUMENTS are never pruned)."""
    got = _PRUNED.get(id(fn))
    if got is None:
        got = set()
        for x in ast.walk(fn):
            if _resolver_call(x):
                got.add(id(x))
                got |= {id(y) for y in ast.walk(x.func)}
        _PRUNED[id(fn)] = got
    return got


def _bound_from(nodes, text):
    keyed = set()
    changed = True
    while changed:
        changed = False
        for n in nodes:
            pairs = []
            if isinstance(n, ast.Assign):
                pairs = [(t, n.value) for t in n.targets]
            elif isinstance(n, (ast.For, ast.comprehension)):
                pairs = [(n.target, n.iter)]
            elif isinstance(n, ast.NamedExpr):
                pairs = [(n.target, n.value)]
            for tg, v in pairs:
                if _value_reads(v, keyed, text):
                    for x in ast.walk(tg):
                        if isinstance(x, ast.Name) and x.id not in keyed:
                            keyed.add(x.id)
                            changed = True
    return keyed


def _plain_text(x):
    """A string literal that is not a dotted identifier."""
    return (isinstance(x, ast.Constant) and isinstance(x.value, str)
            and not all(p.isidentifier() for p in x.value.split(".")))


def sites(fn):
    """[(kind, line)] of the resolution sites in fn's own span."""
    nodes = _own(fn)
    keyed = _bound_from(nodes, False)
    texts = _bound_from(nodes, True)
    pruned = _pruned(fn)
    out = []
    for n in nodes:
        if id(n) in pruned:
            continue
        if isinstance(n, ast.Call):
            f = n.func
            starred = any(isinstance(a, ast.Starred) for a in n.args) or any(
                k.arg is None for k in n.keywords)
            if (isinstance(f, ast.Name) and f.id in ("getattr", "hasattr")
                    and (starred or (len(n.args) >= 2
                    and not isinstance(n.args[1], ast.Constant)
                    and (_reads(n.args[1], keyed) or any(
                        isinstance(x, ast.Attribute) and x.attr == "attr"
                        for x in _walk(n.args[1])))))):
                out.append(("getattr", n.lineno))
            elif ast.unparse(f).endswith("import_module") or (
                    isinstance(f, ast.Name) and f.id == "__import__"):
                out.append(("import", n.lineno))
            elif (isinstance(f, ast.Attribute) and f.attr == "get" and n.args
                  and _reads(n.args[0], keyed)):
                out.append(("table", n.lineno))
            elif isinstance(f, ast.Attribute) and _reads(f.value, keyed):
                # round 9 (G3): a method of a walked identifier
                # (`n.id.startswith(...)`) decides on its spelling
                out.append(("spelling", n.lineno))
        elif (isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Load)
              and _reads(n.slice, keyed)):
            out.append(("table", n.lineno))
        elif isinstance(n, ast.Match) and _reads(n.subject, keyed):
            out.append(("spelling", n.lineno))
        elif isinstance(n, ast.Compare):
            # round 9 (G3): every comparison operator, `is` and the
            # orderings included (round 8 counted ==, !=, in, not in only,
            # so `n.id is 'db'` decided a spelling and counted nothing)
            ops = [n.left] + n.comparators
            if (len(n.ops) == 1 and len(n.comparators) == 1
                    and isinstance(n.ops[0], (ast.Is, ast.IsNot))
                    and isinstance(n.comparators[0], ast.Constant)
                    and n.comparators[0].value is None
                    and not isinstance(n.left, ast.Constant)):
                # `x is None` / `x is not None` decides presence, never a
                # spelling (a spelling is a str, never the None singleton).
                # Round 10 (finding resolution_sites:431): exactly one
                # comparison whose single comparator is the None constant;
                # a chain, or None on the left, is read like any other.
                continue
            if any(_reads(x, keyed) for x in ops):
                out.append(("spelling", n.lineno))
            elif any(isinstance(op, (ast.Eq, ast.NotEq, ast.In, ast.NotIn,
                                     ast.Is, ast.IsNot)) for op in n.ops) and any(
                    _reads(x, texts, True) for x in ops) and any(
                    not _reads(x, texts, True) and not _plain_text(x)
                    for x in ops):
                out.append(("text", n.lineno))
    return out


def walker_spans(tree, walkers_only=True):
    """[(qualname, definition)] of every outermost walker span of module
    tree: each module-level function (outside `test_*` with walkers_only)
    and each method of a module-level class; a nested definition is a part
    of the span that holds it."""
    out = []
    for c in tree.body:
        if isinstance(c, ast.ClassDef):
            out.extend((f"{c.name}.{d.name}", d) for d in c.body
                       if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)))
        elif isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not (walkers_only and c.name.startswith("test_")):
                out.append((c.name, c))
    return out


def grammar_refusals(tree, shapes, filename, walkers_only=True):
    """[(file, line, shape)] for every node of every walker span outside the
    frozen `shapes`; empty when the walker code is in its grammar. The
    walker code holds no annotated assignment, so no AnnAssign shape is in
    WALKER_SHAPES and every one refuses (the census test asserts that no
    frozen shape names AnnAssign)."""
    out = []
    for _q, d in walker_spans(tree, walkers_only):
        out.extend(_sg.refusals(d, shapes, filename))
    return out


def walker_nodes(tree, walkers_only=True):
    """The number of nodes the census grammar checks in module tree."""
    return sum(len(_sg.visit(d)) for _q, d in walker_spans(tree, walkers_only))


def census(tree, methods, walkers_only=True):
    """{(qualname, line): (all sites, sites inside the resolver, sites)}
    for every walker span of module tree (every function, or with
    walkers_only every function outside a `test_*` function); `methods`
    the resolver's method names (resolver_methods of closed_walk). A call
    is the resolver's only on the receiver the span admits (round 9, G2:
    span_receiver over the module's frozen receivers)."""
    receivers = module_receivers(tree)
    RESOLVER_METHODS.clear()
    RESOLVER_METHODS.update(methods)
    _PRUNED.clear()
    out = {}

    def walk(node, prefix, in_resolver):
        for c in ast.iter_child_nodes(node):
            if isinstance(c, ast.ClassDef):
                walk(c, prefix + c.name + ".",
                     in_resolver or c.name == RESOLVER_CLASS)
            elif isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if walkers_only and not prefix and c.name.startswith("test_"):
                    continue
                if prefix.count(".") <= 1 and (
                        not prefix or isinstance(node, ast.ClassDef)):
                    _RECEIVER["spelling"] = span_receiver(
                        receivers, prefix + c.name, c)
                s = sites(c)
                out[(prefix + c.name, c.lineno)] = (
                    len(s), len(s) if in_resolver else 0, s)
                walk(c, prefix + c.name + ".", in_resolver)
            else:
                walk(c, prefix, in_resolver)

    walk(tree, "", False)
    return out


if __name__ == "__main__":
    import sys
    methods = resolver_methods(
        ast.parse(open(sys.argv[1], encoding="utf-8").read()))
    for path in sys.argv[1:]:
        tree = ast.parse(open(path, encoding="utf-8").read())
        tot = 0
        for ln, why in form_problems(tree):
            print(f"{path}:{ln} form: {why}")
        for (q, ln), (a, r, s) in sorted(census(tree, methods).items(),
                                         key=lambda kv: kv[0][1]):
            if a != r:
                tot += a - r
                print(f"{path.split('/')[-1]}:{ln} {q}: {a - r} outside: "
                      + ", ".join(f"{k}@{x}" for k, x in
                                  sorted(s, key=lambda t: t[1])))
        print(f"== {path.split('/')[-1]}: {tot} sites outside the resolver")
