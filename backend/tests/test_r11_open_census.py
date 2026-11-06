"""The DSN census's grammar, round 11 (ruling FOUR-R10-A2 (3) FIX-R11-OPEN,
findings F5 and F6). The grammar is the FILTER; the runtime bound
(test_r11_open_bound_pg, ro_census.OpenRecorder) is the guarantee.

F6: the binding-form list (ro_census.BINDING_FIELDS) is DERIVED here from
the ast module, independently of ro_census: every concrete node class of
_ast (its ASDL signature read from the class's own docstring), every field
of ASDL type identifier or expr, a probe name placed in that field and every
other field filled neutrally, the node wrapped in the smallest module its
category allows, unparsed, re-parsed (the probe must still sit in that class
and field: a round trip), and the compiler's symbol table (symtable) asked
whether the probe name is BOUND (assigned, imported, a parameter or a
namespace) in any scope. The census's list must equal the derived set both
ways, so a binding form cannot be left out by hand.

F5: a reflective literal (a string constant spelled __x__, such as the
'__dict__' of getattr(_asyncpg, '__dict__')) is a form of the grammar.

Runs without a database.
"""

import _ast
import ast
import itertools
import os
import re
import symtable
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import ro_census  # noqa: E402
import ro_census_frozen  # noqa: E402


# ------------------------------------------------------- the derivation
SIG = re.compile(r"^(\w+)(?:\((.*)\))?$")
PROBE = "zz_probe"
_n = itertools.count()


def asdl(cls):
    """[(type, arity, field)] from the class's ASDL signature, or None for an
    abstract category."""
    doc = (cls.__doc__ or "").strip().splitlines()
    m = SIG.match(doc[0].strip()) if doc else None
    if not m or m.group(1) != cls.__name__:
        return None
    out = []
    for part in filter(None, [p.strip() for p in (m.group(2) or "").split(",")]):
        typ, name = part.split()
        out.append((typ.rstrip("?*"), typ[-1] if typ[-1] in "?*" else "", name))
    return out


def node_classes():
    out = {}
    for k, v in vars(_ast).items():
        if isinstance(v, type) and issubclass(v, ast.AST) and v is not ast.AST:
            sig = asdl(v)
            if sig is not None:
                out[k] = (v, sig)
    return out


def category(cls):
    for base in cls.__mro__[1:]:
        if issubclass(base, ast.AST) and base is not ast.AST and asdl(base) is None:
            return base.__name__
    return cls.__name__


def fresh():
    return "nn%d" % next(_n)


def nexpr(kind):
    if kind == "const":
        return ast.Constant(0)
    if kind == "attr":
        return ast.Attribute(ast.Name(fresh(), ast.Load()), fresh(), ast.Load())
    return ast.Name(fresh(), ast.Load())


SIMPLE = {"boolop": ast.And, "operator": ast.Add, "unaryop": ast.Not, "cmpop": ast.Eq,
          "expr_context": ast.Load}


def neutral(typ, q, o):
    """A neutral value of ASDL type `typ` (arity q) under options o."""
    if q == "?" and o["opt"] == "none":
        return None
    if q == "*":
        return [neutral(typ, "", o) for _ in range(o["len"])]
    if typ in ("identifier", "string"):
        return fresh()
    if typ == "int":
        return o["int"]
    if typ == "constant":
        return 0
    if typ == "expr":
        return nexpr(o["expr"])
    if typ in SIMPLE:
        return SIMPLE[typ]()
    if typ == "stmt":
        return ast.Pass()
    if typ == "pattern":
        return ast.MatchAs(None, fresh())
    if typ == "arguments":
        return ast.arguments([], [], None, [], [], None, [])
    if typ == "arg":
        return ast.arg(fresh())
    if typ == "keyword":
        return ast.keyword(fresh(), nexpr("name"))
    if typ == "alias":
        return ast.alias(fresh())
    if typ == "withitem":
        return ast.withitem(nexpr("name"), None)
    if typ == "match_case":
        return ast.match_case(ast.MatchAs(None, fresh()), None, [ast.Pass()])
    if typ == "excepthandler":
        return ast.ExceptHandler(None, None, [ast.Pass()])
    if typ == "comprehension":
        return ast.comprehension(ast.Name(fresh(), ast.Store()), nexpr("name"), [], 0)
    if typ == "type_param":
        return ast.TypeVar(fresh())
    if typ == "type_ignore":
        return ast.TypeIgnore(1, "")
    raise KeyError(typ)


def probe_values(typ):
    if typ == "identifier":
        return [PROBE]
    return [ast.Name(PROBE, ast.Load()),
            ast.Attribute(ast.Name(PROBE, ast.Load()), fresh(), ast.Load()),
            ast.FormattedValue(ast.Name(PROBE, ast.Load()), -1, None),
            ast.JoinedStr([ast.FormattedValue(ast.Name(PROBE, ast.Load()), -1, None)])]


def holders(node, cat):
    yield node
    if cat == "pattern":
        yield ast.MatchSequence([node])
    if cat == "expr":
        yield ast.Subscript(nexpr("name"), node, ast.Load())
        yield ast.JoinedStr([node])


def wrap(node, cat):
    if cat == "stmt":
        return [node]
    if cat == "expr":
        return [ast.Expr(node)]
    if cat == "pattern":
        return [ast.Match(nexpr("name"), [ast.match_case(node, None, [ast.Pass()])])]
    if cat == "excepthandler":
        return [ast.Try([ast.Pass()], [node], [], [])]
    if cat == "arguments":
        return [ast.FunctionDef(fresh(), node, [ast.Pass()], [], None, None, [])]
    if cat == "arg":
        return wrap(ast.arguments([], [node], None, [], [], None, []), "arguments")
    if cat == "keyword":
        return [ast.Expr(ast.Call(nexpr("name"), [], [node]))]
    if cat == "alias":
        return [ast.Import([node])]
    if cat == "withitem":
        return [ast.With([node], [ast.Pass()], None)]
    if cat == "match_case":
        return [ast.Match(nexpr("name"), [node])]
    if cat == "comprehension":
        return [ast.Expr(ast.ListComp(nexpr("name"), [node]))]
    if cat == "type_param":
        return [ast.TypeAlias(ast.Name(fresh(), ast.Store()), [node], nexpr("name"))]
    if cat == "type_ignore":
        return None
    raise KeyError(cat)


def _fn(name, body, cls=ast.FunctionDef):
    return cls(name, ast.arguments([], [], None, [], [], None, []), body, [], None, None, [])


def enclosures(stmts):
    """(module statements, the table name the check starts under or None)."""
    yield stmts, None
    yield [_fn(fresh(), stmts)], None
    yield [_fn(fresh(), stmts, ast.AsyncFunctionDef)], None
    inner = fresh()
    yield [_fn(fresh(), [ast.Assign([ast.Name(PROBE, ast.Store())], ast.Constant(0)),
                         _fn(inner, stmts)])], inner


def _has_probe(v):
    if isinstance(v, str):
        return v == PROBE
    if isinstance(v, list):
        return any(_has_probe(x) for x in v)
    if isinstance(v, ast.AST):
        return any(isinstance(x, ast.Name) and x.id == PROBE for x in ast.walk(v))
    return False


def round_trips(src, cname, field):
    return any(type(n).__name__ == cname and _has_probe(getattr(n, field, None))
               for n in ast.walk(ast.parse(src)))


def bound(src, within):
    tables = [symtable.symtable(src, "<probe>", "exec")]
    if within is not None:
        found, stack = [], list(tables)
        while stack:
            t = stack.pop()
            if t.get_name() == within:
                found.append(t)
            stack.extend(t.get_children())
        tables = found
    while tables:
        t = tables.pop()
        try:
            s = t.lookup(PROBE)
        except KeyError:
            s = None
        if s is not None and (s.is_assigned() or s.is_imported() or s.is_parameter()
                              or s.is_namespace()):
            return True
        tables.extend(t.get_children())
    return False


def probe(cname, field, classes):
    cls, sig = classes[cname]
    cat = category(cls)
    typ = next(t for t, _q, f in sig if f == field)
    last = "no variant built"
    for n, ek, opt, iv, pv in itertools.product((1, 2), ("name", "const", "attr"),
                                                ("none", "filled"), (-1, 0, 1),
                                                probe_values(typ)):
        o = {"expr": ek, "opt": opt, "int": iv, "len": n}
        kw = {f: ([pv] + [neutral(t, "", o) for _ in range(n - 1)] if qq == "*" else pv)
              if f == field else neutral(t, qq, o) for t, qq, f in sig}
        try:
            node = cls(**kw)
        except Exception as e:  # noqa: BLE001
            last = repr(e)
            continue
        for h in holders(node, cat):
            stmts = wrap(h, cat)
            if stmts is None:
                return None, "no module context for category %s" % cat
            for body, within in enclosures(stmts):
                try:
                    src = ast.unparse(ast.fix_missing_locations(ast.Module(body, [])))
                    if not round_trips(src, cname, field):
                        last = "did not round-trip: %r" % src[:80]
                        continue
                    return bound(src, within), src
                except Exception as e:  # noqa: BLE001
                    last = "%s: %s" % (type(e).__name__, e)
    return None, last


def derive():
    classes = node_classes()
    binding, unprobed = set(), {}
    for cname, (cls, sig) in sorted(classes.items()):
        if cname == "Expression":
            # the eval root: its one expr field probed in eval mode
            src = ast.unparse(ast.Expression(ast.Name(PROBE, ast.Load())))
            if symtable.symtable(src, "<probe>", "eval").lookup(PROBE).is_assigned():
                binding.add((cname, "body"))
            continue
        if category(cls) == "mod":
            # FunctionType: the func_type root of a signature type comment;
            # symtable has no such mode (Module and Interactive hold only
            # statements, probed in their own classes)
            for t, _q, f in sig:
                if t in ("identifier", "expr"):
                    unprobed[(cname, f)] = "a root (mod) field"
            continue
        for t, _q, f in sig:
            if t not in ("identifier", "expr"):
                continue
            b, info = probe(cname, f, classes)
            if b is None:
                unprobed[(cname, f)] = info
            elif b:
                binding.add((cname, f))
    return binding, unprobed


# ------------------------------------------------------------------ the tests

def test_r11_binding_forms_equal_the_derived_set():
    """F6: the census's binding-form list is the derived set, both ways, and
    the forms the derivation cannot probe are the census's declared ones."""
    binding, unprobed = derive()
    assert ("NamedExpr", "target") in binding     # the form round 10 left out
    assert binding == set(ro_census.BINDING_FIELDS), (
        "derived, not in the census: %s; in the census, not derived: %s"
        % (sorted(binding - ro_census.BINDING_FIELDS),
           sorted(ro_census.BINDING_FIELDS - binding)))
    assert set(unprobed) == set(ro_census.UNPROBED_FIELDS), unprobed


def test_r11_derivation_is_the_symbol_table():
    """The derivation's verdicts come from the compiler: fields that hold a
    name without binding it are probed and come back unbound (an attribute
    name, a keyword name, an imported-from module, a global declaration, a
    class pattern's attribute names, a loaded Name)."""
    classes = node_classes()
    for cname, field in (("Attribute", "attr"), ("keyword", "arg"), ("ImportFrom", "module"),
                         ("Global", "names"), ("MatchClass", "kwd_attrs"), ("Name", "id"),
                         ("Call", "func"), ("Subscript", "value")):
        verdict, info = probe(cname, field, classes)
        assert verdict is False, (cname, field, verdict, info)
    for cname, field in (("NamedExpr", "target"), ("ExceptHandler", "name"),
                         ("MatchAs", "name"), ("withitem", "optional_vars")):
        verdict, info = probe(cname, field, classes)
        assert verdict is True, (cname, field, verdict, info)


CF_PG = "tests/cf_pg.py"
DATABASE = "api/database.py"
# (with its newline: release_engine's line ends with the same text)
ENGINE_LINE = "\nengine = create_async_engine(\n    DATABASE_URL,"


def _src(rel):
    with open(os.path.join(BACKEND, rel), encoding="utf-8") as fh:
        return fh.read()


def _refused(rel, text):
    frozen = {k: ro_census_frozen.FROZEN[k] for k in (rel, rel + ro_census.COMPLETE)}
    return ro_census.diff(ro_census.file_forms(rel, text), frozen), frozen


def test_r11_grammar_refuses_the_dict_alias_opener():
    """F5 (ro_census.py:473): the round-10 report's text, planted in cf_pg.py,
    is refused by the grammar (a reflective literal is a form); the unplanted
    file is clean."""
    src = _src(CF_PG)
    plant = ("\n\nasync def _planted(dsn):\n"
             "    table = getattr(_asyncpg, '__dict__')\n"
             "    dial = table['con' + 'nect']\n"
             "    return await dial(dsn)\n")
    refused, frozen = _refused(CF_PG, src + plant)
    assert ro_census.diff(ro_census.file_forms(CF_PG, src), frozen) == []
    assert refused and all(r[1] == "+" for r in refused), refused
    assert (CF_PG + ro_census.COMPLETE, "+", "alias", "str __dict__") in refused, refused


# Every binding form of a forwarded module-scope name (DATABASE_URL reaches
# create_async_engine at database.py's engine line), planted just before the
# engine line: each must be refused as an argdef form.
REBINDINGS = (
    ("walrus", "(DATABASE_URL := DATABASE_URL.replace('comp_rounds', 'scr_gate'))\n"),
    ("walrus_in_test", "if (DATABASE_URL := DATABASE_URL.replace('comp_rounds', 'g')):\n"
                       "    pass\n"),
    ("walrus_in_comprehension",
     "[(DATABASE_URL := u) for u in [DATABASE_URL.replace('comp_rounds', 'g')]]\n"),
    ("except_as", "try:\n    pass\nexcept Exception as DATABASE_URL:\n    pass\n"),
    ("match_capture", "match DATABASE_URL.replace('comp_rounds', 'g'):\n"
                      "    case DATABASE_URL:\n        pass\n"),
    ("match_star", "match [DATABASE_URL]:\n    case [*DATABASE_URL]:\n        pass\n"),
    ("match_rest", "match {}:\n    case {**DATABASE_URL}:\n        pass\n"),
    ("for_target", "for DATABASE_URL in [DATABASE_URL.replace('comp_rounds', 'g')]:\n"
                   "    pass\n"),
    ("with_target", "with open(__file__) as DATABASE_URL:\n    pass\n"),
    ("import_as", "import os as DATABASE_URL\n"),
    ("type_alias", "type DATABASE_URL = str\n"),
    ("annotated", "DATABASE_URL: str = 'postgresql://scr_gate@h/d'\n"),
)


@pytest.mark.parametrize("name", [r[0] for r in REBINDINGS])
def test_r11_grammar_refuses_every_rebinding(name):
    """F6 (ro_census.py:307): each binding form of DATABASE_URL before the
    engine construction is refused (an argdef form naming its statement)."""
    plant = dict(REBINDINGS)[name]
    src = _src(DATABASE)
    assert src.count(ENGINE_LINE) == 1
    refused, frozen = _refused(DATABASE, src.replace(ENGINE_LINE, "\n" + plant + ENGINE_LINE[1:]))
    assert ro_census.diff(ro_census.file_forms(DATABASE, src), frozen) == []
    argdefs = [r for r in refused if r[2] == "argdef" and r[3].startswith("DATABASE_URL <- ")]
    assert argdefs and all(r[1] == "+" for r in refused), refused


def test_r11_comprehension_target_is_not_a_module_binding():
    """Scope, the filter's precision: a comprehension's own target binds in
    the comprehension, so it is no argdef form of the module name (the
    walrus row above is the binding form that does reach the module)."""
    src = _src(DATABASE)
    plant = "[DATABASE_URL for DATABASE_URL in ()]\n"
    assert src.count(ENGINE_LINE) == 1
    refused, _frozen = _refused(DATABASE, src.replace(ENGINE_LINE, "\n" + plant + ENGINE_LINE[1:]))
    assert not [r for r in refused if r[2] == "argdef"], refused
