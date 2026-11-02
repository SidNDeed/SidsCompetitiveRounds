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
`<name>.b.<method>(...)` (the visitor's `self.b.callee(...)`, the gate
walk's `w.b.named(...)`). Every other call is an ordinary expression,
its value read for KEY and TEXT: `b.named(...)` on a plain name (round 7
admitted any receiver, so `return b.named(n.id) == 'db'` counted no
site), the visitor's `self._check(...)` and `self._resolve(...)`,
`Bindings(...).<method>(...)`. The resolver call's ARGUMENTS are read
like any other expression of the span (round 7, finding
resolution_sites:132: a decision evaluated inside a resolver call's
argument contributed no site).

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
    `<name>.b.<method>(...)` with <method> one class Bindings defines."""
    if not isinstance(x, ast.Call):
        return False
    f = x.func
    return (isinstance(f, ast.Attribute) and f.attr in RESOLVER_METHODS
            and isinstance(f.value, ast.Attribute) and f.value.attr == "b"
            and isinstance(f.value.value, ast.Name))


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


def _reads(e, keyed, text=False):
    """Whether e is KEY (text False) or TEXT (text True)."""
    for x in _walk(e):
        if not text and isinstance(x, ast.Attribute) and x.attr == "id":
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
        if not text and isinstance(x, ast.Attribute) and x.attr == "id":
            return True
        if text and _is_unparse(x):
            return True
        if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load) and x.id in keyed:
            return True
    return False


def _own(fn):
    """fn's nodes outside nested definitions and lambdas."""
    out, todo = [], list(ast.iter_child_nodes(fn))
    while todo:
        n = todo.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                          ast.Lambda)):
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
            if (isinstance(f, ast.Name) and f.id == "getattr" and len(n.args) >= 2
                    and not isinstance(n.args[1], ast.Constant)
                    and (_reads(n.args[1], keyed) or any(
                        isinstance(x, ast.Attribute) and x.attr == "attr"
                        for x in _walk(n.args[1])))):
                out.append(("getattr", n.lineno))
            elif ast.unparse(f).endswith("import_module"):
                out.append(("import", n.lineno))
            elif (isinstance(f, ast.Attribute) and f.attr == "get" and n.args
                  and _reads(n.args[0], keyed)):
                out.append(("table", n.lineno))
        elif (isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Load)
              and _reads(n.slice, keyed)):
            out.append(("table", n.lineno))
        elif isinstance(n, ast.Compare) and any(
                isinstance(op, (ast.Eq, ast.NotEq, ast.In, ast.NotIn))
                for op in n.ops):
            ops = [n.left] + n.comparators
            if any(_reads(x, keyed) for x in ops):
                out.append(("spelling", n.lineno))
            elif any(_reads(x, texts, True) for x in ops) and any(
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
    the resolver's method names (resolver_methods of closed_walk)."""
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
        for (q, ln), (a, r, s) in sorted(census(tree, methods).items(),
                                         key=lambda kv: kv[0][1]):
            if a != r:
                tot += a - r
                print(f"{path.split('/')[-1]}:{ln} {q}: {a - r} outside: "
                      + ", ".join(f"{k}@{x}" for k, x in
                                  sorted(s, key=lambda t: t[1])))
        print(f"== {path.split('/')[-1]}: {tot} sites outside the resolver")
