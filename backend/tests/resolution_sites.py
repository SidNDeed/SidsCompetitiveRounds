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
    stores = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute)
              and n.attr == "b" and not isinstance(n.ctx, ast.Load)]
    init = [d for c in tree.body if isinstance(c, ast.ClassDef) and c.name == cls
            for d in c.body if isinstance(d, ast.FunctionDef)
            and d.name == "__init__"]
    good = [n for n in stores if init and isinstance(n.value, ast.Name)
            and n.value.id == "self" and isinstance(par.get(id(n)), ast.Assign)
            and any(n is x for x in ast.walk(init[0]))
            and any(isinstance(c, ast.Call) and ast.unparse(c.func).split(".")[-1]
                    == RESOLVER_CLASS for c in ast.walk(par[id(n)].value))]
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
            if all(isinstance(op, (ast.Is, ast.IsNot)) for op in n.ops) and any(
                    isinstance(x, ast.Constant) and x.value is None for x in ops):
                # `x is None` / `x is not None` decides presence, never a
                # spelling (a spelling is a str, never the None singleton)
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
