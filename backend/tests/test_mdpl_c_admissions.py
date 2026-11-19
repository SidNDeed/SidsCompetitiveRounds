"""MDPL class C: the controls of the hand edit of grammar_shapes_a1.py and of the signal-class route of
closed_walk.py (the integrator's rulings of 17 Nov 2026: 09:13:52Z, 10:05:30Z, 10:12:24Z and 10:53:36Z).

1. ADMISSIONS. The 22 admitted shapes: the twelve of the five a1 spans the lane changed, and the ten of the three
   lane helpers the real walks reach. For each, at its first site in visit order in its span:
   - the real span is admitted by the full frozen grammar;
   - without that one shape, the grammar refuses the real span, naming the shape at that site;
   - a near variant (one field of that one node changed) is planted there. The variant is outside A1_SHAPES, and
     the full grammar refuses the planted span by that shape at that site.
2. PLACEMENT (condition 1). Four plants of the lane's shapes at a1 spans the lane did not change. The shape rule
   alone admits each plant; the full grammar refuses each by its order or position rule.
3. VACATED KEYS (condition 2). Every A1 span, found by name in its file, is admitted by the full grammar. The
   UPDATE's SQL text is planted at a position the lane's insertion vacated (_credit_bet_fighter_tax body[3]). The
   position rule refuses it; with that one key restored it is admitted.
4. SIGNAL CLASSES, through the walk's own route (Bindings.namedtuple_class) over main, at the line of a real
   construction in _deletion_lock_party_row:
   - both classes are admitted;
   - refused: a third main.py exception class; a twin class statement in another module; the class statement,
     the uses or the name row taken out of or changed in the frozen rows; a member added or replaced; the base
     class changed;
   - the frozen lines and the frozen uses equal main's;
   - every condition of the admission has its own plant (MDPL class C2), each breaking that one condition, each
     refused by its whole sentence, the real class admitted again after it: a class made by a metaclass (a); an
     object main does not bind to the name (b); the class under another qualified name (c); a member of the frozen
     statement taken off (d); a member whose code differs in its first line alone (e), in its file alone (f), or a
     function on the real code under another qualified name (g).
5. r7's READ-ONLY CENSUS (rulings of 11:01:25Z and 19 Nov 07:50:20Z): the 25 forms of ro_census_frozen.MDPL_FROZEN.
   - main.py, closed_walk.py and test_a1_identity_formation.py census clean against the freeze;
   - the freeze less the block flags exactly the block's 25 forms;
   - a near variant planted in the same block stays flagged, one form each: one more __qualname__ read, a new
     dunder read and vars() of another object in the signal route, and one more setattr in the attempt's
     arming; a plain statement at the same place, its twin, flags nothing.
Parts 1 to 3 and 5 read the source files alone. Part 4 imports main, as the a1 walks do."""

import ast
import copy
import linecache
import os
import sys
import types

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.join(HERE, "..", "api")
sys.path.insert(0, API)
sys.path.insert(0, HERE)

import closed_walk as cw  # noqa: E402
import grammar_shapes_a1 as gs  # noqa: E402
import shape_grammar as sg  # noqa: E402
from closed_walk import Unclassified  # noqa: E402

FIVE = ("_credit_bet_fighter_tax", "_credit_team_bet_fighter_tax", "_return_stake_exactly",
        "_reconcile_team_series_bets", "_service_player_uuids")
THREE = ("_deletion_bound_acts_on", "_retryable_for_caller", "_deletion_lock_party_row")
SIGNALS = ("_DeletionRowHeld", "_DeletionPastDeadline")
THIRD = "_IdentityBudgetSpent"   # another plain Exception subclass of main.py, outside the frozen rows

_TREES = {}


def _defs(filename):
    """{name: [definitions]} of api/`filename`, every function at any depth (parsed once)."""
    if filename not in _TREES:
        with open(os.path.join(API, filename), encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=filename)
        out = {}
        for d in ast.walk(tree):
            if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.setdefault(d.name, []).append(d)
        _TREES[filename] = out
    return _TREES[filename]


def _span(name, filename="main.py"):
    hits = _defs(filename)[name]
    assert len(hits) == 1, (filename, name, len(hits))
    return copy.deepcopy(hits[0])


def _grammar(shapes=None, allowed=None, namedtuples=None):
    return cw.Grammar(gs.A1_SHAPES if shapes is None else shapes, gs.A1_MEANINGFUL,
                      gs.A1_BINDINGS if allowed is None else allowed, {},
                      gs.A1_NAMEDTUPLES if namedtuples is None else namedtuples)


def _verdict(d, **kw):
    try:
        _grammar(**kw).admit(d, "main.py")
        return "admitted"
    except Unclassified as e:
        return e.args[0][1]


def _site(d, shape):
    """The first node of span `d`, in visit order, whose shape is `shape`: (node, parent, field, line)."""
    for n, p, f in sg.visit(d):
        if sg.shape(n, p, f) == shape:
            return n, p, f, sg._line(n, p)
    raise AssertionError("no node of %s has the shape %s" % (d.name, shape))


def _set(field, make):
    def mutate(n):
        setattr(n, field, make(n))
    return mutate


def _attr_of(name):
    return ast.Attribute(value=ast.Name(id="main", ctx=ast.Load()), attr=name, ctx=ast.Load())


_ARGS = "AsyncFunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[arg],"
# (span, admitted shape, mutation of the node at its first site, the near variant it makes)
ADMISSIONS = (
    ("_reconcile_team_series_bets",
     _ARGS + "kw_defaults=[Constant],kwarg=-,defaults=[Constant|Name])",
     _set("kwarg", lambda n: ast.arg(arg="mdpl_c_rest")),
     _ARGS + "kw_defaults=[Constant],kwarg=arg,defaults=[Constant|Name])"),
    ("_credit_bet_fighter_tax",
     _ARGS + "kw_defaults=[Constant],kwarg=-,defaults=[Constant])",
     _set("kwarg", lambda n: ast.arg(arg="mdpl_c_rest")),
     _ARGS + "kw_defaults=[Constant],kwarg=arg,defaults=[Constant])"),
    ("_credit_team_bet_fighter_tax",
     _ARGS + "kw_defaults=[Constant],kwarg=-,defaults=[Tuple])",
     _set("kwarg", lambda n: ast.arg(arg="mdpl_c_rest")),
     _ARGS + "kw_defaults=[Constant],kwarg=arg,defaults=[Tuple])"),
    ("_return_stake_exactly",
     _ARGS + "kw_defaults=[Constant|NoneType],kwarg=-,defaults=[])",
     _set("kwarg", lambda n: ast.arg(arg="mdpl_c_rest")),
     _ARGS + "kw_defaults=[Constant|NoneType],kwarg=arg,defaults=[])"),
    ("_reconcile_team_series_bets",
     "arguments.defaults>Constant(value=bool)",
     _set("value", lambda n: 0),
     "arguments.defaults>Constant(value=int)"),
    ("_service_player_uuids",
     "Try.handlers>ExceptHandler(type=Tuple,name=-,body=[Raise])",
     _set("name", lambda n: "mdpl_c_e"),
     "Try.handlers>ExceptHandler(type=Tuple,name=str,body=[Raise])"),
    ("_service_player_uuids",
     "ExceptHandler.type>Tuple(elts=[Name],ctx=Load)",
     _set("elts", lambda n: [_attr_of(n.elts[0].id)] + n.elts[1:]),
     "ExceptHandler.type>Tuple(elts=[Attribute|Name],ctx=Load)"),
    ("_credit_bet_fighter_tax",
     "Call.keywords>keyword(arg='no_wait',value=Name)",
     _set("value", lambda n: ast.Constant(value=True)),
     "Call.keywords>keyword(arg='no_wait',value=Constant)"),
    ("_reconcile_team_series_bets",
     "Await.value>Call(func=Name,args=[Call|Name|Subscript],keywords=[keyword])",
     _set("func", lambda n: _attr_of(n.func.id)),
     "Await.value>Call(func=Attribute,args=[Call|Name|Subscript],keywords=[keyword])"),
    ("_reconcile_team_series_bets",
     "Try.handlers>ExceptHandler(type=Name,name=str,body=[Expr|If])",
     _set("name", lambda n: None),
     "Try.handlers>ExceptHandler(type=Name,name=-,body=[Expr|If])"),
    ("_reconcile_team_series_bets",
     "ExceptHandler.body>If(test=Call,body=[Raise],orelse=[])",
     _set("orelse", lambda n: [ast.Pass()]),
     "ExceptHandler.body>If(test=Call,body=[Raise],orelse=[Pass])"),
    ("_reconcile_team_series_bets",
     "If.body>Raise(exc=-,cause=-)",
     _set("exc", lambda n: ast.Name(id="ex", ctx=ast.Load())),
     "If.body>Raise(exc=Name,cause=-)"),
    ("_deletion_bound_acts_on",
     "BoolOp.values>Compare(left=Name,ops=[In],comparators=[Name])",
     _set("comparators", lambda n: [ast.Call(func=ast.Name(id="frozenset", ctx=ast.Load()),
                                             args=[n.comparators[0]], keywords=[])]),
     "BoolOp.values>Compare(left=Name,ops=[In],comparators=[Call])"),
    ("_deletion_bound_acts_on",
     "BoolOp.values>Compare(left=Name,ops=[In],comparators=[Tuple])",
     _set("ops", lambda n: [ast.NotIn()]),
     "BoolOp.values>Compare(left=Name,ops=[NotIn],comparators=[Tuple])"),
    ("_retryable_for_caller",
     "FunctionDef.body>If(test=Call,body=[Return],orelse=[])",
     _set("orelse", lambda n: [ast.Pass()]),
     "FunctionDef.body>If(test=Call,body=[Return],orelse=[Pass])"),
    ("_retryable_for_caller",
     "Return.value>BoolOp(op=And,values=[Call])",
     _set("op", lambda n: ast.Or()),
     "Return.value>BoolOp(op=Or,values=[Call])"),
    ("_retryable_for_caller",
     "BoolOp.values>Call(func=Name,args=[Call],keywords=[])",
     _set("keywords", lambda n: [ast.keyword(arg="mdpl_c", value=ast.Constant(value=1))]),
     "BoolOp.values>Call(func=Name,args=[Call],keywords=[keyword])"),
    ("_retryable_for_caller",
     "Call.args>Call(func=Name,args=[Call|Constant],keywords=[])",
     _set("func", lambda n: _attr_of(n.func.id)),
     "Call.args>Call(func=Attribute,args=[Call|Constant],keywords=[])"),
    ("_deletion_lock_party_row",
     "AsyncFunctionDef.body>If(test=Compare,body=[Assign|If|Return],orelse=[])",
     _set("orelse", lambda n: [ast.Pass()]),
     "AsyncFunctionDef.body>If(test=Compare,body=[Assign|If|Return],orelse=[Pass])"),
    ("_deletion_lock_party_row",
     "If.body>If(test=Compare,body=[Raise],orelse=[])",
     _set("orelse", lambda n: [ast.Pass()]),
     "If.body>If(test=Compare,body=[Raise],orelse=[Pass])"),
    ("_deletion_lock_party_row",
     "If.test>Compare(left=Subscript,ops=[Is],comparators=[Constant])",
     _set("comparators", lambda n: [ast.Name(id="mdpl_c_none", ctx=ast.Load())]),
     "If.test>Compare(left=Subscript,ops=[Is],comparators=[Name])"),
    ("_deletion_lock_party_row",
     "UnaryOp.operand>BoolOp(op=And,values=[Compare])",
     _set("op", lambda n: ast.Or()),
     "UnaryOp.operand>BoolOp(op=Or,values=[Compare])"),
)


def test_the_admissions_are_the_twenty_two_and_in_the_grammar():
    shapes = [s for _sp, s, _m, _v in ADMISSIONS]
    assert len(shapes) == len(set(shapes)) == 22
    assert set(shapes) <= gs.A1_SHAPES
    assert {sp for sp, _s, _m, _v in ADMISSIONS} == set(FIVE) | set(THREE)
    assert not ({v for _sp, _s, _m, v in ADMISSIONS} & gs.A1_SHAPES)


@pytest.mark.parametrize("span,shape,mutate,variant", ADMISSIONS,
                         ids=["%02d %s" % (i + 1, a[0]) for i, a in enumerate(ADMISSIONS)])
def test_admission_is_needed_and_its_near_variant_is_refused(span, shape, mutate, variant):
    real = _span(span)
    assert _verdict(real) == "admitted", span
    _n, _p, _f, line = _site(real, shape)
    print("ADMISSION %s at main.py:%d in %s" % (shape, line, span))
    without = _verdict(_span(span), shapes=gs.A1_SHAPES - {shape})
    assert without == "a shape outside the grammar at main.py:%d: %s" % (line, shape), without
    d = _span(span)
    n, p, f, at = _site(d, shape)
    mutate(n)
    ast.fix_missing_locations(d)
    assert sg.shape(n, p, f) == variant and variant not in gs.A1_SHAPES
    got = _verdict(d)
    assert got == "a shape outside the grammar at main.py:%d: %s" % (at, variant), got
    print("NEAR VARIANT %s at main.py:%d: refused: %s" % (variant, at, got))


# --- 2. placement (condition 1) ---------------------------------------------------------------------------------

def _unchanged_spans():
    out = []
    for f, _ln, name, _n in gs.A1_SPANS:
        if f == "main.py" and name not in FIVE + THREE:
            out.append(name)
    return out


def _keyword_plant(d):
    for n in ast.walk(d):
        if (isinstance(n, ast.Await) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)
                and not n.value.keywords and n.value.args and all(isinstance(a, ast.Name) for a in n.value.args)):
            n.value.keywords.append(ast.copy_location(
                ast.keyword(arg="no_wait", value=ast.Name(id=n.value.args[-1].id, ctx=ast.Load())), n.value))
            yield n.lineno


def _tuple_handler_plant(d):
    for n in ast.walk(d):
        if isinstance(n, ast.Try) and n.handlers:
            h = ast.ExceptHandler(type=ast.Tuple(elts=[ast.Name(id=s, ctx=ast.Load()) for s in SIGNALS],
                                                 ctx=ast.Load()), name=None, body=[ast.Raise(exc=None, cause=None)])
            n.handlers.insert(0, ast.copy_location(h, n.handlers[0]))
            yield n.handlers[0].lineno


def _bare_raise_plant(d):
    for n in ast.walk(d):
        if isinstance(n, ast.If) and len(n.body) == 1 and isinstance(n.body[0], ast.Raise) and n.body[0].exc:
            n.body[0] = ast.copy_location(ast.Raise(exc=None, cause=None), n.body[0])
            yield n.body[0].lineno


def _handler_if_plant(d):
    for n in ast.walk(d):
        if (isinstance(n, ast.ExceptHandler) and isinstance(n.type, ast.Name) and n.name
                and len(n.body) == 1 and isinstance(n.body[0], ast.Expr)):
            test = ast.Call(func=ast.Name(id="_retryable_for_caller", ctx=ast.Load()),
                            args=[ast.Name(id=n.name, ctx=ast.Load()), ast.Name(id=n.name, ctx=ast.Load())],
                            keywords=[])
            n.body.insert(0, ast.copy_location(ast.If(test=test, body=[ast.Raise(exc=None, cause=None)],
                                                      orelse=[]), n.body[0]))
            yield n.body[0].lineno


SHAPE_ONLY = gs.A1_BINDINGS - {cw.POSITIONED, cw.ORDERED}


@pytest.mark.parametrize("plant,shape", [
    (_keyword_plant, "Call.keywords>keyword(arg='no_wait',value=Name)"),
    (_tuple_handler_plant, "Try.handlers>ExceptHandler(type=Tuple,name=-,body=[Raise])"),
    (_bare_raise_plant, "If.body>Raise(exc=-,cause=-)"),
    (_handler_if_plant, "ExceptHandler.body>If(test=Call,body=[Raise],orelse=[])"),
], ids=["no_wait keyword", "tuple handler with a bare raise", "a bare raise in an If", "handler body Expr and If"])
def test_a_lane_shape_planted_in_an_unchanged_span_is_refused_by_its_place(plant, shape):
    """The first site, over the unchanged a1 spans in A1_SPANS order, where the plant holds the lane's shape and the
    shape rule alone admits the planted span; there the full grammar refuses it by the order or position rule."""
    for name in _unchanged_spans():
        d = _span(name)
        for at in plant(d):
            ast.fix_missing_locations(d)
            if shape in sg.shapes(d) and _verdict(d, allowed=SHAPE_ONLY) == "admitted":
                got = _verdict(d)
                print("PLACEMENT %s planted at main.py:%d in %s: shape rule alone: admitted; full grammar: %s"
                      % (shape, at, name, got))
                assert got.startswith("the anchored rule at main.py:") and (
                    "outside its frozen order" in got or "outside its frozen position" in got), got
                return
            break
    raise AssertionError("no unchanged span takes the plant with the shape rule alone: %s" % shape)


# --- 3. vacated keys (condition 2) ------------------------------------------------------------------------------

def test_every_a1_span_is_admitted_by_the_full_grammar():
    got = {}
    for f, _ln, name, _n in gs.A1_SPANS:
        got[(f, name)] = _verdict(_span(name, f))
    assert len(got) == len(gs.A1_SPANS) == 68
    assert {k: v for k, v in got.items() if v != "admitted"} == {}


_VACATED_SQL = "UPDATE players SET gold_earned = COALESCE(gold_earned,0) + :tax WHERE id = :pid"
_VACATED = (repr(_VACATED_SQL), "const", "_credit_bet_fighter_tax",
            ("body[3]", "value", "value", "args[0]", "args[0]"))


def test_a_constant_at_a_vacated_position_is_refused_and_admitted_with_its_key():
    assert _VACATED not in gs.A1_BINDINGS
    d = _span("_credit_bet_fighter_tax")
    call = d.body[3].value.value
    assert isinstance(call, ast.Call) and call.func.id == "_deletion_lock_party_row", ast.dump(call)[:160]
    call.args[0] = ast.copy_location(ast.Call(func=ast.Name(id="text", ctx=ast.Load()),
                                              args=[ast.Constant(value=_VACATED_SQL)], keywords=[]), call.args[0])
    ast.fix_missing_locations(d)
    no_orders = gs.A1_BINDINGS - {cw.ORDERED}
    own = "binds %s (def)" % d.name
    after = [w for _f, _l, w in cw.anchored_refusals(d, gs.A1_MEANINGFUL, no_orders, "main.py") if w != own]
    restored = [w for _f, _l, w in cw.anchored_refusals(d, gs.A1_MEANINGFUL, no_orders | {_VACATED}, "main.py")
                if w != own]
    print("VACATED after the removal: %s | with the key restored: %s" % (after, restored))
    assert len(after) == 1 and "a constant outside its frozen position" in after[0] and (
        str(_VACATED[3]) in after[0]), after
    assert restored == []
    assert _verdict(d) != "admitted"


# --- 4. the signal classes --------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def main_mod():
    import main
    return main


def _construction():
    """The span and the line of _deletion_lock_party_row's construction of _DeletionRowHeld."""
    d = _span("_deletion_lock_party_row")
    hits = [n for n in ast.walk(d) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "_DeletionRowHeld"]
    assert hits
    return d, hits[0].lineno


def _route(scope, name, namedtuples=None):
    d, line = _construction()
    b = cw.Bindings(scope, d, grammar=_grammar(namedtuples=namedtuples))
    node = ast.Name(id=name, ctx=ast.Load())
    node.lineno = line
    try:
        return b.namedtuple_class(node, line), line
    except Unclassified as e:
        return e.args[0][1], line


# Without its name row a class takes the named-tuple route, which refuses main's whole module by its root shape
# (_admitted_scope); measured, whole.
OUTSIDE_THE_SCOPE = (": a shape outside the definition scope at main.py:0: <root>>Module(body=[AnnAssign|Assert|"
                     "Assign|AsyncFunctionDef|ClassDef|Expr|FunctionDef|Import|ImportFrom|Try],type_ignores=[])")


@pytest.mark.parametrize("name", SIGNALS)
def test_the_signal_class_is_admitted_by_the_route(main_mod, name):
    got, line = _route(main_mod, name)
    print("SIGNAL %s at main.py:%d: %r" % (name, line, got))
    assert got is getattr(main_mod, name)


def test_a_third_main_exception_class_is_refused(main_mod):
    assert issubclass(getattr(main_mod, THIRD), Exception)
    assert ("<signal class>", THIRD) not in gs.A1_NAMEDTUPLES
    got, line = _route(main_mod, THIRD)
    print("THIRD %s at main.py:%d: %s" % (THIRD, line, got))
    assert got == THIRD + OUTSIDE_THE_SCOPE, got


def _text_of(name):
    return getattr(gs, "_SIGNAL_TEXT" + name.upper())


def test_a_twin_class_statement_in_another_module_is_refused(monkeypatch, main_mod):
    text = _text_of("_DeletionRowHeld") + "\n"
    twin = types.ModuleType("mdpl_c_twin")
    twin.__file__ = "<mdpl_c_twin>"
    linecache.cache[twin.__file__] = (len(text), None, text.splitlines(True), twin.__file__)
    monkeypatch.setitem(sys.modules, twin.__name__, twin)
    exec(compile(text, twin.__file__, "exec"), twin.__dict__)
    assert twin._DeletionRowHeld is not main_mod._DeletionRowHeld
    got, line = _route(twin, "_DeletionRowHeld")
    print("TWIN at <mdpl_c_twin>, route line %d: %s" % (line, got))
    assert got == "_DeletionRowHeld: its class statement in <mdpl_c_twin> is not its frozen signal class", got


def _rows_without(pred):
    return frozenset(r for r in gs.A1_NAMEDTUPLES if not pred(r))


def _is_signal_row(name, kind):
    def pred(r):
        if not (isinstance(r, tuple) and len(r) >= 2 and r[0] == "<signal class>" and r[1] == name):
            return False
        if kind == "name":
            return len(r) == 2
        if kind == "statement":
            return len(r) == 4
        return len(r) == 5 and r[3] == "uses"
    return pred


@pytest.mark.parametrize("name", SIGNALS)
def test_the_name_row_is_what_admits(main_mod, name):
    got, _line = _route(main_mod, name, _rows_without(_is_signal_row(name, "name")))
    print("NAME ROW of %s out: %s" % (name, got))
    assert got == name + OUTSIDE_THE_SCOPE, got


@pytest.mark.parametrize("name", SIGNALS)
def test_a_changed_class_statement_is_refused(main_mod, name):
    edited = _text_of(name).replace('"""', '"""Edited. ', 1)
    assert edited != _text_of(name)
    rows = _rows_without(_is_signal_row(name, "statement")) | {
        ("<signal class>", name, "main.py", ast.dump(ast.parse(edited).body[0]))}
    got, _line = _route(main_mod, name, rows)
    print("STATEMENT of %s changed: %s" % (name, got))
    assert got == "%s: its class statement in main.py is not its frozen signal class" % name, got


@pytest.mark.parametrize("name", SIGNALS)
def test_a_changed_use_is_refused(main_mod, name):
    old = [r for r in gs.A1_NAMEDTUPLES if _is_signal_row(name, "uses")(r)]
    assert len(old) == 1
    rows = _rows_without(_is_signal_row(name, "uses")) | {old[0][:4] + (old[0][4][:-1],)}
    got, _line = _route(main_mod, name, rows)
    print("USES of %s less their last row: %s" % (name, got))
    assert got == "%s: its uses in main.py are not its frozen uses" % name, got


def test_a_member_added_or_replaced_is_refused(monkeypatch, main_mod):
    cls = main_mod._DeletionRowHeld
    with monkeypatch.context() as m:
        m.setattr(cls, "mdpl_c_extra", lambda self: None, raising=False)
        got, _line = _route(main_mod, "_DeletionRowHeld")
    print("MEMBER added: %s" % got)
    assert got == "_DeletionRowHeld: its member mdpl_c_extra is not its frozen statement's", got

    def __init__(self, what):
        Exception.__init__(self, what)
        self.what = what
    __init__.__qualname__ = "_DeletionRowHeld.__init__"
    with monkeypatch.context() as m:
        m.setattr(cls, "__init__", __init__)
        got, _line = _route(main_mod, "_DeletionRowHeld")
    print("MEMBER replaced: %s" % got)
    assert got == "_DeletionRowHeld: its member __init__ is not its frozen statement's", got
    assert _route(main_mod, "_DeletionRowHeld")[0] is cls


def test_a_changed_base_is_refused(main_mod):
    # set and restored by hand: monkeypatch would restore a type slot by deleting it, which Python refuses
    cls = main_mod._DeletionPastDeadline
    assert cls.__bases__ == (Exception,)
    cls.__bases__ = (RuntimeError,)
    try:
        got, _line = _route(main_mod, "_DeletionPastDeadline")
    finally:
        cls.__bases__ = (Exception,)
    print("BASE changed to RuntimeError: %s" % got)
    assert got == "_DeletionPastDeadline: not a plain Exception subclass", got
    assert cls.__bases__ == (Exception,)
    assert _route(main_mod, "_DeletionPastDeadline")[0] is cls


# MDPL class C2: one plant per condition of _signal_class (a to g, the integrator's order of 18 Nov 17:44:44Z, 3).
# Each breaks that ONE condition and passes every other (a mutant of closed_walk.py that takes the condition out
# admits the plant), asserts its whole sentence, restores what it changed, and the route admits the real class again.
# The plants use _DeletionRowHeld, whose frozen statement defines one function, __init__.

HELD = "_DeletionRowHeld"
NOT_ITS_MODULES = HELD + ": not the class its module defines"
NOT_ITS_STATEMENTS = HELD + ": its member __init__ is not its frozen statement's"


def _like(cls, meta=type):
    """A new class made by `meta` with cls's name, module, qualified name, docstring and bases, and cls's own
    functions as its members: the plain mro, and in main the name's real class statement and uses."""
    ns = {"__module__": cls.__module__, "__qualname__": cls.__qualname__, "__doc__": cls.__doc__}
    ns.update((k, v) for k, v in vars(cls).items() if isinstance(v, types.FunctionType))
    made = meta(cls.__name__, cls.__bases__, ns)
    assert made is not cls and made.__mro__ == (made, Exception, BaseException, object)
    assert made.__qualname__ == cls.__qualname__ == HELD and made.__module__ == "main"
    own = {k: v for k, v in vars(cls).items() if k not in cw._SIGNAL_SET_ASIDE}
    assert {k: v for k, v in vars(made).items() if k not in cw._SIGNAL_SET_ASIDE} == own == {
        "__init__": vars(cls)["__init__"]}
    return made


# a. identity, no metaclass
def test_a_class_made_by_a_metaclass_is_refused(monkeypatch, main_mod):
    cls = getattr(main_mod, HELD)
    meta = type("_MdplC2Meta", (type,), {})
    made = _like(cls, meta)
    assert type(made) is meta
    with monkeypatch.context() as m:
        m.setattr(main_mod, HELD, made)
        got, _line = _route(main_mod, HELD)
    print("METACLASS: %s" % (got,))
    assert got == NOT_ITS_MODULES, got
    assert getattr(main_mod, HELD) is cls
    assert _route(main_mod, HELD)[0] is cls


# b. identity, the module's own binding
def test_an_object_its_module_does_not_bind_is_refused(main_mod):
    cls = getattr(main_mod, HELD)
    made = _like(cls)
    assert type(made) is type and getattr(main_mod, HELD) is cls
    scope = types.ModuleType("mdpl_c2_scope")
    setattr(scope, HELD, made)
    got, _line = _route(scope, HELD)
    print("NOT MAIN'S BINDING: %s" % (got,))
    assert got == NOT_ITS_MODULES, got
    assert _route(main_mod, HELD)[0] is cls


# c. identity, the qualified name
def test_the_class_under_another_qualified_name_is_refused(main_mod):
    # set and restored by hand: monkeypatch would restore a type slot by deleting it, which Python refuses
    cls = getattr(main_mod, HELD)
    assert cls.__qualname__ == HELD
    cls.__qualname__ = "_MdplC2Outer." + HELD
    try:
        got, _line = _route(main_mod, HELD)
    finally:
        cls.__qualname__ = HELD
    print("QUALNAME changed: %s" % (got,))
    assert got == NOT_ITS_MODULES, got
    assert cls.__qualname__ == HELD
    assert _route(main_mod, HELD)[0] is cls


# d. members, none missing
def test_a_member_taken_off_is_missing(monkeypatch, main_mod):
    cls = getattr(main_mod, HELD)
    real = vars(cls)["__init__"]
    with monkeypatch.context() as m:
        m.delattr(cls, "__init__")
        assert "__init__" not in vars(cls)
        got, _line = _route(main_mod, HELD)
    print("MEMBER taken off: %s" % (got,))
    assert got == HELD + ": its member __init__ is missing", got
    assert vars(cls)["__init__"] is real
    assert _route(main_mod, HELD)[0] is cls


def _function(fn, code=None, qualname=None):
    """A new function on `code` (fn's own by default) with fn's globals, name, defaults and closure, under
    `qualname` (fn's by default)."""
    made = types.FunctionType(code or fn.__code__, fn.__globals__, fn.__name__, fn.__defaults__, fn.__closure__)
    made.__qualname__ = qualname or fn.__qualname__
    return made


def _elsewhere(code):
    return os.path.join(os.path.dirname(code.co_filename), "mdpl_c2_elsewhere.py")


# e, f, g: a member that differs from the real one in ONE of the three things _signal_member compares
MEMBER_PLANTS = {
    "e-line": lambda fn: _function(fn, code=fn.__code__.replace(co_firstlineno=fn.__code__.co_firstlineno + 1)),
    "f-file": lambda fn: _function(fn, code=fn.__code__.replace(co_filename=_elsewhere(fn.__code__))),
    "g-qualname": lambda fn: _function(fn, qualname="_DeletionPastDeadline.__init__"),
}


@pytest.mark.parametrize("which", list(MEMBER_PLANTS))
def test_a_member_differing_in_one_thing_is_refused(monkeypatch, main_mod, which):
    cls = getattr(main_mod, HELD)
    real = vars(cls)["__init__"]
    made = MEMBER_PLANTS[which](real)
    c, r = made.__code__, real.__code__
    differ = [k for k, x, y in (("e-line", c.co_firstlineno, r.co_firstlineno),
                                ("f-file", os.path.basename(c.co_filename), os.path.basename(r.co_filename)),
                                ("g-qualname", made.__qualname__, real.__qualname__)) if x != y]
    assert differ == [which], differ
    with monkeypatch.context() as m:
        m.setattr(cls, "__init__", made)
        got, _line = _route(main_mod, HELD)
    print("MEMBER %s: %s" % (which, got))
    assert got == NOT_ITS_STATEMENTS, got
    assert vars(cls)["__init__"] is real
    assert _route(main_mod, HELD)[0] is cls


def test_the_frozen_lines_and_uses_are_mains(main_mod):
    defs = {d.name: d.lineno for d in ast.parse(open(os.path.join(API, "main.py"), encoding="utf-8").read()).body
            if isinstance(d, ast.ClassDef)}
    assert [(f, defs[n], n) for f, _l, n in gs.A1_SIGNAL_LINES] == list(gs.A1_SIGNAL_LINES)
    for f, name, rows in gs.A1_SIGNAL_USES:
        assert f == "main.py" and tuple(cw._n_census(main_mod, name)) == tuple(rows), name


# ---------------------------------------------------------------------------
# 5. r7's read-only census (rulings of 17 Nov 11:01:25Z, 19 Nov 07:50:20Z): MDPL_FROZEN's 25 forms, frozen by hand.

import ro_census  # noqa: E402
import ro_census_frozen as fz  # noqa: E402

BACKEND = os.path.dirname(HERE)
R7_FILES = ("api/main.py", "tests/closed_walk.py", "tests/test_a1_identity_formation.py")


def _r7_source(rel):
    with open(os.path.join(BACKEND, rel), encoding="utf-8") as fh:
        return fh.read()


def _r7_diff(rel, source, frozen=None):
    """The census of one file's two layers against the freeze's rows for them."""
    frozen = fz.FROZEN if frozen is None else frozen
    got = ro_census.file_forms(rel, source)
    return ro_census.diff(got, {k: frozen.get(k, []) for k in got})


def _plant_after(source, anchor, line):
    """`source` with `line` inserted, at the anchor's indent, after the one line that reads `anchor`; and the
    planted line's number."""
    lines = source.split("\n")
    at = [i for i, x in enumerate(lines) if x.strip() == anchor]
    assert len(at) == 1, (anchor, at)
    head = lines[at[0]]
    indent = head[:len(head) - len(head.lstrip())]
    return "\n".join(lines[:at[0] + 1] + [indent + line] + lines[at[0] + 1:]), at[0] + 2


def test_r7_the_three_files_census_clean_with_the_block():
    for rel in R7_FILES:
        assert _r7_diff(rel, _r7_source(rel)) == [], rel


def test_r7_the_block_is_what_admits_its_25_forms():
    bare = {k: list(v) for k, v in fz.FROZEN.items()}
    for k, v in fz.MDPL_FROZEN.items():
        for form in v:
            bare[k].remove(form)
    got = [r for rel in R7_FILES for r in _r7_diff(rel, _r7_source(rel), bare)]
    want = [(k, "+") + tuple(f) for k, v in fz.MDPL_FROZEN.items() for f in v]
    assert sorted(got) == sorted(want), got
    assert len(got) == fz.MDPL_COUNT == 25


R7_PLANTS = (
    # (name, file, anchor line, planted line, the one form the census must flag)
    ("one more __qualname__ read", "tests/closed_walk.py", "members = vars(obj)",
     '_q = getattr(obj, "__qualname__", None)',
     ("tests/closed_walk.py#complete", "+", "alias", "str __qualname__")),
    ("a new dunder read", "tests/closed_walk.py", "members = vars(obj)",
     '_s = getattr(obj, "__subclasses__", None)',
     ("tests/closed_walk.py#complete", "+", "alias", "str __subclasses__")),
    ("vars() of another object", "tests/closed_walk.py", "members = vars(obj)",
     "_m = vars(home)",
     ("tests/closed_walk.py#complete", "+", "dynamic", "vars(home)")),
    ("one more setattr in the arming", "api/main.py", "setattr(db, name, fn)",
     "setattr(db, name, fn)",
     ("api/main.py#complete", "+", "dynamic", "setattr(db, name, fn)")),
)


@pytest.mark.parametrize("name", [p[0] for p in R7_PLANTS])
def test_r7_a_near_variant_in_the_block_stays_flagged(name):
    _n, rel, anchor, line, want = next(p for p in R7_PLANTS if p[0] == name)
    src = _r7_source(rel)
    planted, at = _plant_after(src, anchor, line)
    got = _r7_diff(rel, planted)
    print("R7 PLANT %s at %s:%d: %s" % (name, os.path.basename(rel), at, got))
    assert got == [want], got
    twin, _at = _plant_after(src, anchor, "_t = name")
    assert _r7_diff(rel, twin) == []
