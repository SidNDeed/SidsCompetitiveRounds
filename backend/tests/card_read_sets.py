"""What each card measure READS, derived from card_measures.py's own code by
a static read-set analysis of the function bodies. It never looks at the
coverage catalog (card_measures.NEEDS); the tests check the catalog against
it: for every measure, DECLARED (NEEDS) must contain READ.

READ(m) is the set of coverage facts (card_measures.COVER) whose data the
computation of measure m reads:
  - a record list a fact certifies (cards, held0, ph, hd, ap) is read as a
    whole -- its length, a search or lookup in it, a count or accumulation
    over it, a test of it -- and that read depends on the list being whole;
    one entry taken by iteration is exact whatever else was trimmed, so a
    per-entry field read alone does not depend on the list's fact; an entry
    taken by position or by a computed index does (a trim moves positions);
  - a hand entry's slot list and spawn list (positions sl and sp of an hd
    entry) are read at all: any read of either depends on sl / sp, and a
    whole read of an hd entry reads both;
  - the record's loss and fault bits and its semantics word: whole; its
    first-phase bit and the first-phase picking order: first;
  - the record's stated omission counts: the fact each one names.
A value carries its facts through every operation, function call (each
argument into the parameter, each return out), attribute of the record
facts object, dict field, and control decision: the tests of every if,
early return and continue in force where a value is assigned, and the
iteration count of every loop the value accumulates across. A control
decision is left out of a definition only where it governs every use that
definition reaches and none of those uses is a return (it then decides
whether the value exists, never which value it holds).

DEFAULT DENY. The analysis models an explicit allowlist and refuses
everything else (Unsupported), so an unmodelled shape fails the proof
instead of reading as nothing:
  - statements: STMTS; any other statement kind is refused where the walk
    meets it (Fn._walk, the one place; the exit scan of an if refuses a
    break or a nested definition first, on its own);
  - expressions: EXPRS, dispatched by node class in Analysis.ev; any other
    expression kind is refused there (the one place; the definition scan
    refuses a lambda or an assignment expression first, on its own);
  - calls: the builtins of TRUTH/CONTENT/PICK/KEEP/PAIR_BUILTINS and dict,
    the module calls of MODULE_CALLS, the scalar methods of SCALAR_METHODS,
    the dict and list methods MUTATORS, get and KEEP_METHODS, and every
    function and class method of card_measures (analysed in turn); any
    other callable is refused, and a module function or class used as a
    value is refused;
  - values: every label a record-derived value carries says what it is (a
    record, the omission counts, a window aggregate, a list of a record
    list's entries, one entry, a measure row, a dict of fields, a holder of
    those); each operation has a rule per label, and a label an operation
    has no rule for is refused: a whole read (an operator, a comparison, a
    module call, a measure's value) of a record, a measure row or a field
    dict; a dynamic key into the record, a measure row or a field dict;
    a positional read of the record; an attribute of record data, or a
    method of it outside the modelled ones; a record list placed inside
    another container; an hd entry unpacked into the wrong width; hd
    entries given to enumerate or zip anywhere but straight into the
    targets of a for or a comprehension (modelled per target there).
  - measure rows, the write side: a measure key the analysis cannot resolve
    is refused when it is WRITTEN (a subscript store into a measure row, a
    literal mixing measure keys with an unresolved key, a merge or a
    mutation of a measure row by anything but another measure row) as when
    it is READ; a dict reaches the gate, a measure-row name or window_row's
    return only if it is a measure row the analysis built.
Every merge is a union, so imprecision only ever adds facts.

Why it is complete (the proof refuses rather than under-reads):
  - every function reachable from the entries (card_view, contributions,
    window_row) is analysed, to a fixpoint over all of them; a function that
    writes a measure key and is not reachable fails the analysis;
  - every statement and expression form has an explicit rule; any other form
    raises Unsupported;
  - every record key, omission key, field key and attribute read must have a
    known source; an unknown one raises Unsupported;
  - every measure of MEASURES must have at least one definition site, and
    every measure-like string in the code must be a measure or a piece of a
    measure name pattern;
  - variables are tracked per definition with reaching definitions
    (structural dominance kills only), parameters per function over every
    call site, dict fields per key over the whole module: each merge is a
    union, so imprecision only ever adds facts.
Excluded by construction, and only these: the gate itself (_gate and
covered, which enforce NEEDS); the record's coverage statement (the ok
dict, which only the gate and the coverage counters read, and the incident
word read whole rather than one bit through its mask: `statements` lists
every measure that carries it); and a test of whether a measure IS None
(its NOT-RUN state, from the gate or from the measure's own code, which the
not-run counters count); `drops` lists every place that last exclusion
applied. The second method (card_read_dynamic) sees each excluded read and
the tests check each one is exactly what the exclusion names."""

import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
if API not in sys.path:
    sys.path.insert(0, API)

import card_measures as cm  # noqa: E402

SOURCE = os.path.join(API, "card_measures.py")
ENTRIES = ("card_view", "contributions", "window_row")
GATE = ("_gate", "covered")
COVERAGE_ATTR = ("RecFacts", "ok")
MODULES = ("math", "hashlib", "json", "re")

# -- the modeled callables, each with its read semantics -----------------------------
# a count, a truth value or a type test: the facts a test of the value reads
TRUTH_BUILTINS = {"len", "bool", "isinstance"}
# a whole read of every argument
CONTENT_BUILTINS = {"sum", "any", "all", "abs", "int", "str", "float", "divmod", "round", "hash",
                    "repr", "ord", "chr", "range", "type"}
# one element chosen from the argument (by order or position): the element,
# plus a whole read of every element the choice compared
PICK_BUILTINS = {"next", "min", "max"}
# the same elements in another container; over a dict, its keys
KEEP_BUILTINS = {"sorted", "list", "set", "tuple", "frozenset", "reversed", "iter"}
# tuples of elements: modeled when unpacked straight into a for target
PAIR_BUILTINS = {"enumerate", "zip"}
DICT_BUILTIN = "dict"
# module functions: a whole read of every argument
MODULE_CALLS = {("math", "sqrt"), ("hashlib", "sha256"), ("json", "dumps")}
# methods of a scalar (a string, a digest): a whole read of receiver and arguments
SCALAR_METHODS = {"encode", "hexdigest"}
MUTATORS = {"append", "add", "extend", "update", "insert", "setdefault"}
KEEP_METHODS = {"items", "values", "keys", "copy"}
BUILTIN_VALUES = (TRUTH_BUILTINS | CONTENT_BUILTINS | PICK_BUILTINS | KEEP_BUILTINS | PAIR_BUILTINS
                  | {DICT_BUILTIN})

MEAS = {n for names in cm.MEASURES.values() for n in names}
FACTS = tuple(cm.COVER)
LISTS = ("cards", "held0", "ph", "hd", "ap")
# where a stored record's top-level keys lead: a fact-certified list, the
# first-phase order, the omission counts, or data no fact covers
REC_KEYS = {key: set() for key in cm.W["keys"]}
REC_KEYS.update({key: {"C:" + key} for key in LISTS})
REC_KEYS.update({"po": {"F:first"}, "omit": {"O"}, "inc": {"INCW"}})
# the incident word's bits, each read through its mask (INC[...]): the fact
# each certifies; the word read whole is the record's own coverage statement
INC_KEYS = {"lost": {"F:whole"}, "fault": {"F:whole"}, "first": {"F:first"},
            "all": {"F:whole", "F:first"}}
INCW, STATEMENT = "INCW", "S:inc"
SCALAR = ("F:", "M:", "S:")
INPUT_KEYS = {"rec": {"R"}, "seat": set(), "other": set(), "conflict": set()}

# Labels. Facts: F:<fact> (the value depends on the fact), M:<measure> (on
# that measure's value), S:inc (on the incident word read whole: the
# record's coverage statement, excluded like ok and listed by `statements`).
# Lists: C:<list> (a list of that record list's entries), E:<list> (one
# entry of it), N:<fact> (a container whose length or membership depends on
# the fact; its elements are not entries), Q:<fact> (a container whose
# elements are such containers). INCW: the incident word itself.
# Structures: R the record, O its omission counts, AGG a window aggregate,
# SELF the method's object, ROW a measure row (built here with measure keys),
# D a dict read by field (a measure row or a dict of fields), DS a list or
# tuple that may hold such dicts, DD a dict whose values may hold them.
AGG = "AGG"
REC, OMIT, SELF = "R", "O", "SELF"
ROW, D, DS, DD = "ROW", "D", "DS", "DD"
KEYED = (ROW, D)
HOLDERS = (DS, DD)
DICTS = (REC, OMIT, AGG, ROW, D, DD)


class Unsupported(Exception):
    """A construct the analysis has no rule for: refused, never read as
    nothing."""


def _plain(ls):
    out = set()
    for x in ls:
        if x[:2] in ("C:", "N:", "Q:"):
            out.add("F:" + x[2:])
        elif x[:2] in SCALAR:
            out.add(x)
        elif x == INCW:
            out.add(STATEMENT)
    return out


def _cify(ls):
    return {("N:" + x[2:]) if x.startswith("F:") else x for x in _plain(ls)}


def _const(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int)):
        return node.value
    if (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub)
            and isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, int)):
        return -node.operand.value
    return None


def _exits(st):
    """(has a return or raise, has a continue of this loop) anywhere under
    the if statement, nested function bodies excluded."""
    ret = cont = False
    stack = list(st.body) + list(st.orelse)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.Return, ast.Raise)):
            ret = True
        elif isinstance(n, ast.Continue):
            cont = True
        elif isinstance(n, ast.Break):
            raise Unsupported("break at line %d" % n.lineno)
        elif isinstance(n, ast.For):
            for m in ast.walk(n):
                if isinstance(m, (ast.Return, ast.Raise)):
                    ret = True
            continue
        if isinstance(n, (ast.FunctionDef, ast.Lambda, ast.ClassDef)):
            raise Unsupported("nested definition at line %d" % n.lineno)
        if isinstance(n, ast.stmt):
            stack.extend(ast.iter_child_nodes(n))
    return ret, cont


# The statement kinds the walk models; Fn._walk refuses every other kind.
STMTS = (ast.Assign, ast.AugAssign, ast.Expr, ast.Return, ast.If, ast.For, ast.Continue, ast.Pass,
         ast.Raise)


class Fn:
    """One function: its statements in walk order with the control decisions
    in force at each, and every definition and use of each variable."""

    def __init__(self, key, node, cls=None):
        self.key, self.node, self.cls = key, node, cls
        if not isinstance(node, ast.FunctionDef) or node.decorator_list:
            raise Unsupported("definition form of " + key)
        a = node.args
        if a.vararg or a.kwarg or a.kwonlyargs or a.posonlyargs:
            raise Unsupported("signature of " + key)
        names = [x.arg for x in a.args]
        self.self_name = names[0] if cls else None
        self.params = names[1:] if cls else names
        self.defaults = dict(zip(names[len(names) - len(a.defaults):], a.defaults))
        self.stmts, self.guards, self.defs, self.alias = [], [], {}, {}
        self.uses, self.escapes = {}, set()
        self.measure_vars = set()
        for p in self.params:
            self.defs.setdefault(p, []).append((-1, True))
        self._exit_guards = []
        self._walk(node.body, (), (), [], [[]])

    def _guard(self, kind, expr, site, outer):
        self.guards.append({"kind": kind, "expr": expr, "site": site, "outer": tuple(outer),
                            "governed": set()})
        return len(self.guards) - 1

    def _walk(self, body, chain, loops, active, conts):
        for i, st in enumerate(body):
            if type(st) not in STMTS:
                raise Unsupported("no rule for the statement %s at line %d in %s"
                                  % (type(st).__name__, getattr(st, "lineno", 0), self.key))
            idx = len(self.stmts)
            act = tuple(active) + tuple(self._exit_guards) + tuple(g for c in conts for g in c)
            here = chain + ((id(body), i),)
            self.stmts.append({"node": st, "chain": here, "loops": loops, "guards": act})
            for g in act:
                self.guards[g]["governed"].add(idx)
            self._names(st, idx)
            if isinstance(st, ast.If):
                gid = self._guard("if", st.test, idx, act)
                self._walk(st.body, here, loops, active + [gid], conts)
                self._walk(st.orelse, here, loops, active + [gid], conts)
                ret, cont = _exits(st)
                if ret:
                    self._exit_guards.append(self._guard("exit", st.test, idx, act))
                if cont:
                    if not loops:
                        raise Unsupported("continue outside a loop in " + self.key)
                    conts[-1].append(self._guard("exit", st.test, idx, act))
            elif isinstance(st, ast.For):
                if st.orelse:
                    raise Unsupported("for-else in " + self.key)
                gid = self._guard("for", st.iter, idx, act)
                self._walk(st.body, here, loops + (idx,), active + [gid], conts + [[]])

    def _target_names(self, t, idx, kill):
        if isinstance(t, ast.Name):
            self.defs.setdefault(t.id, []).append((idx, kill))
        elif isinstance(t, (ast.Tuple, ast.List)):
            for e in t.elts:
                self._target_names(e, idx, kill)
        elif isinstance(t, ast.Subscript):
            base = t.value
            while isinstance(base, ast.Subscript):
                base = base.value
            if isinstance(base, ast.Name):
                self._mut(base.id, idx)
            if isinstance(t.value, ast.Name):
                key = _const(t.slice)
                if isinstance(key, str) and key in MEAS:
                    self.measure_vars.add(t.value.id)
        elif isinstance(t, ast.Attribute):
            pass
        else:
            raise Unsupported("target at line %d" % t.lineno)

    def _mut(self, name, idx):
        """A change to the object `name` holds: a definition of it, and of
        every name it was taken from (c = out.setdefault(...): out too)."""
        while True:
            self.defs.setdefault(name, []).append((idx, False))
            if name not in self.alias:
                return
            name = self.alias[name]

    def _names(self, st, idx):
        if isinstance(st, ast.Return):
            self.escapes.add(idx)
        if isinstance(st, ast.AugAssign) and isinstance(st.target, ast.Name):
            self.uses.setdefault(st.target.id, set()).add(idx)
        if isinstance(st, ast.If):
            exprs = [st.test]
        elif isinstance(st, ast.For):
            exprs = [st.target, st.iter]
            self._target_names(st.target, idx, True)
        else:
            exprs = [st]
        if isinstance(st, ast.Assign):
            for t in st.targets:
                self._target_names(t, idx, True)
            v = st.value
            if (len(st.targets) == 1 and isinstance(st.targets[0], ast.Name)
                    and isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute)
                    and v.func.attr == "setdefault" and isinstance(v.func.value, ast.Name)):
                self.alias[st.targets[0].id] = v.func.value.id
            if (len(st.targets) == 1 and isinstance(st.targets[0], ast.Name) and isinstance(v, ast.Dict)
                    and any(isinstance(_const(kk), str) and _const(kk) in MEAS for kk in v.keys)):
                self.measure_vars.add(st.targets[0].id)
        elif isinstance(st, ast.AugAssign):
            self._target_names(st.target, idx, True)
        for e in exprs:
            for n in ast.walk(e):
                if isinstance(n, ast.Name):
                    if isinstance(n.ctx, ast.Load):
                        self.uses.setdefault(n.id, set()).add(idx)
                elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                      and n.func.attr in MUTATORS and isinstance(n.func.value, ast.Name)):
                    self._mut(n.func.value.id, idx)
                elif isinstance(n, (ast.Lambda, ast.NamedExpr)):
                    raise Unsupported("%s at line %d" % (type(n).__name__, n.lineno))

    def dom(self, k, u):
        """Statement k precedes u in a block that holds u: every path into u
        from outside that block passes k."""
        ck, cu = self.stmts[k]["chain"], self.stmts[u]["chain"]
        d = len(ck) - 1
        if len(cu) <= d or cu[:d] != ck[:d]:
            return False
        return cu[d][0] == ck[d][0] and cu[d][1] > ck[d][1]

    def reaching(self, var, u):
        ds = self.defs.get(var, [])
        kills = [s for s, kill in ds if kill and s >= 0]
        out = []
        for d, _kill in ds:
            if d < u:
                if any(d < k < u and self.dom(k, u) for k in kills):
                    continue
                out.append(d)
            else:
                lu, ld = self.stmts[u]["loops"], self.stmts[d]["loops"]
                common = [x for x in lu if x in ld]
                if not common:
                    continue
                inner = common[-1]
                if any(self.dom(k, u) and inner in self.stmts[k]["loops"] for k in kills):
                    continue
                out.append(d)
        return out


class Analysis:
    def __init__(self, source=None):
        text = source if source is not None else open(SOURCE, encoding="utf-8").read()
        self.tree = ast.parse(text)
        self.fns, self.classes, self.cls_attrs, self.methods = {}, {}, {}, {}
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.fns[node.name] = node
            elif isinstance(node, ast.ClassDef):
                self.classes[node.name] = node
                self.cls_attrs[node.name] = set()
                for m in node.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self.fns[node.name + "." + m.name] = (node.name, m)
                        if m.name != "__init__":
                            self.methods.setdefault(m.name, []).append(node.name + "." + m.name)
                        for n in ast.walk(m):
                            if (isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
                                    and isinstance(n.value, ast.Name) and n.value.id == "self"):
                                self.cls_attrs[node.name].add(n.attr)
        self.built = {}
        self.defl, self.ret, self.attr, self.field = {}, {}, {}, {}
        self.defs, self.sites, self.pieces = {}, {}, set()
        self.drops, self.gate_calls = set(), set()
        self.consts = {}
        self.reach = set(ENTRIES)
        hd = self._fn("_hand_fields")
        unpack = hd.node.body[0].targets[0]
        names = [e.id for e in unpack.elts]
        if len(names) != cm.WIDTH["hd"]:
            raise Unsupported("hand entry width")
        self.positions = {names.index("sl"): "F:sl", names.index("sp"): "F:sp"}
        self.contrib_keys = {_const(kk) for n in ast.walk(self._fn("contributions").node)
                             if isinstance(n, ast.Dict) for kk in n.keys if isinstance(_const(kk), str)}
        # every field key the module writes: a dict literal's constant keys
        # and a constant-key subscript assignment's
        self.field_keys = set()
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Dict):
                self.field_keys |= {_const(kk) for kk in n.keys if isinstance(_const(kk), str)}
            elif isinstance(n, (ast.Assign, ast.AugAssign)):
                for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                    if isinstance(t, ast.Subscript) and isinstance(_const(t.slice), str):
                        self.field_keys.add(_const(t.slice))

    # -- functions --------------------------------------------------------------

    def _fn(self, key):
        if key not in self.built:
            v = self.fns.get(key)
            if v is None:
                raise Unsupported("no function " + key)
            self.built[key] = Fn(key, v[1], v[0]) if isinstance(v, tuple) else Fn(key, v)
        return self.built[key]

    def _add(self, d, key, labels):
        cur = d.setdefault(key, set())
        before = len(cur)
        cur |= labels
        return len(cur) != before

    def _size(self):
        return (sum(len(v) for d in (self.defl, self.ret, self.attr, self.field, self.defs)
                    for v in d.values()) + len(self.reach))

    def run(self):
        # A refusal for a label that IS present holds at any point of the
        # fixpoint (labels only grow); a refusal for a label that is ABSENT
        # (a measure row required where none arrived) is decided only on the
        # converged labels, by one more strict walk.
        self.strict = False
        while True:
            before = self._size()
            self._add(self.defl, ("contributions", "view", -1), self.ret.get("card_view", set()))
            self._add(self.defl, ("window_row", "agg", -1), {AGG})
            for key in sorted(self.reach):
                self._process(self._fn(key))
            if self._size() == before:
                break
        self.strict = True
        for key in sorted(self.reach):
            self._process(self._fn(key))
        if self._size() != before:
            raise Unsupported("the strict walk changed the converged labels")
        self._check()
        return self

    def _need_row(self, ok, what, lineno):
        if self.strict and not ok:
            raise Unsupported("%s at line %d" % (what, lineno))
        return self

    def _bind(self, key, call, fn, site, scopes, skip_first=False):
        if key in GATE:
            self.gate_calls.add(fn.key)
            return
        self.reach.add(key)
        tgt = self._fn(key)
        if any(isinstance(a, ast.Starred) for a in call.args):
            raise Unsupported("starred call at line %d" % call.lineno)
        given = {}
        for p, a in zip(tgt.params, call.args):
            given[p] = self.ev(a, fn, site, scopes)
        if len(call.args) > len(tgt.params):
            raise Unsupported("arity at line %d" % call.lineno)
        for kw in call.keywords:
            if kw.arg is None or kw.arg not in tgt.params:
                raise Unsupported("keyword at line %d" % call.lineno)
            given[kw.arg] = self.ev(kw.value, fn, site, scopes)
        for p in tgt.params:
            if p not in given:
                if p not in tgt.defaults:
                    raise Unsupported("missing argument %s at line %d" % (p, call.lineno))
                given[p] = self.ev(tgt.defaults[p], tgt, -1, ())
            self._add(self.defl, (key, p, -1), given[p])

    # -- the label rules ----------------------------------------------------------
    #
    # One rule per label for each way a value is used. A label a rule does not
    # name is refused: the default is Unsupported, never an empty read.

    def _entry_whole(self, lst):
        """The facts a whole read of one entry of record list `lst` reads."""
        return set(self.positions.values()) if lst == "hd" else set()

    def _content(self, ls, what, lineno):
        """A whole read of a value (an operator, a comparison, a module call,
        a measure's value): every fact its data carries."""
        out = set()
        for x in ls:
            p = x[:2]
            if p in SCALAR:
                out.add(x)
            elif p == "C:":
                out.add("F:" + x[2:])
                out |= self._entry_whole(x[2:])
            elif p in ("N:", "Q:"):
                out.add("F:" + x[2:])
            elif p == "E:":
                out |= self._entry_whole(x[2:])
            elif x == INCW:
                out.add(STATEMENT)
            else:
                raise Unsupported("whole read of a record-derived structure (%s) by %s at line %d"
                                  % (x, what, lineno))
        return out

    def _no_self(self, ls, lineno):
        if SELF in ls:
            raise Unsupported("the object itself read as data at line %d" % lineno)
        return ls

    def _elem(self, ls, lineno):
        """One element taken by iteration."""
        out = set()
        for x in ls:
            p = x[:2]
            if p in SCALAR:
                out.add(x)
            elif p == "C:":
                out.add("E:" + x[2:])
            elif p == "N:":
                continue
            elif p == "Q:":
                out.add("N:" + x[2:])
            elif p == "E:":
                out |= self._entry_whole(x[2:])
            elif x == DS:
                out |= {D, DS}
            elif x in (ROW, D, DD):
                continue                        # a dict yields its keys
            else:
                raise Unsupported("iteration over a record-derived structure (%s) at line %d"
                                  % (x, lineno))
        return out

    def _index(self, ls, key, lineno):
        """One element taken by an integer position (key an int) or by a
        computed key (key None)."""
        out = set()
        for x in ls:
            p = x[:2]
            if p in SCALAR:
                out.add(x)
            elif p == "C:":
                out |= {"F:" + x[2:], "E:" + x[2:]}
            elif p == "N:":
                out.add("F:" + x[2:])
            elif p == "Q:":
                out.add("N:" + x[2:])
            elif p == "E:":
                if key is None:
                    out |= self._entry_whole(x[2:])
                elif x[2:] == "hd":
                    width = cm.WIDTH["hd"]
                    if not -width <= key < width:
                        raise Unsupported("hand entry position %d at line %d" % (key, lineno))
                    if key % width in self.positions:
                        out.add(self.positions[key % width])
            elif x in HOLDERS:
                out |= {D, DS}
            elif x in KEYED:
                if key is None:
                    raise Unsupported("dynamic key into a measure row or field dict at line %d" % lineno)
            elif x == OMIT and key is None:
                out |= {"F:" + k for k in cm.W["omit_keys"]}
            elif x == AGG and key is None:
                out |= self._agg()
            elif x == REC:
                raise Unsupported(("dynamic key into the record at line %d" if key is None
                                   else "positional read of the record at line %d") % lineno)
            else:
                raise Unsupported("%s read of %s at line %d"
                                  % ("computed-key" if key is None else "positional", x, lineno))
        return out

    def _unpack(self, ls, n, lineno):
        """The labels of each of n targets a value is unpacked into."""
        outs = [set() for _ in range(n)]
        rest = set()
        for x in ls:
            if x.startswith("E:"):
                lst = x[2:]
                if n == cm.WIDTH.get(lst):
                    if lst == "hd":
                        for i in range(n):
                            if i in self.positions:
                                outs[i].add(self.positions[i])
                elif lst == "hd":
                    raise Unsupported("a hand entry unpacked into %d targets at line %d" % (n, lineno))
                else:
                    for o in outs:
                        o.add(x)
            else:
                rest.add(x)
        for i in range(n):
            outs[i] |= self._index(rest, i, lineno)
        return outs

    def _pack(self, ls, lineno):
        """A value placed as one element of a list, tuple or set."""
        out = set()
        for x in ls:
            p = x[:2]
            if p == "E:":
                out.add("C:" + x[2:])
            elif p == "C:":
                raise Unsupported("a record list placed inside another container at line %d" % lineno)
            elif p in ("N:", "Q:"):
                out.add("Q:" + x[2:])           # an element whose own length depends on the fact
            elif x in KEYED or x in HOLDERS:
                out.add(DS)
            else:
                out.add(x)
        return out

    def _dpack(self, ls, lineno):
        """A value stored under a computed key of a dict."""
        return {DD if x == DS else x for x in self._pack(ls, lineno)}

    def _key(self, ls, lineno):
        """A value used as a dict key, a set member or an index: a whole read
        of a hashable value (a dict or list is unhashable, so a label of one
        reads nothing here)."""
        rest = {x for x in ls if x not in DICTS and x not in HOLDERS and not x.startswith("E:")}
        return self._content(self._no_self(rest, lineno), "a key", lineno)

    def _keep(self, name, ls, lineno):
        """The elements of a value in another container (KEEP_BUILTINS)."""
        out = set()
        for x in ls:
            if x == SELF:
                raise Unsupported("the object itself read as data at line %d" % lineno)
            if x in DICTS:
                continue                        # a dict's keys
            if x.startswith("E:") and x[2:] == "hd" and name not in ("list", "tuple", "iter"):
                out |= self._entry_whole("hd")  # positions no longer hold
                continue
            out.add(x)
        return out

    def _pick(self, ls, lineno):
        """One element chosen from a value (next, min, max)."""
        out = set()
        for x in ls:
            p = x[:2]
            if p in SCALAR:
                out.add(x)
            elif p == "C:":
                out |= {"F:" + x[2:], "E:" + x[2:]}
            elif p == "N:":
                out.add("F:" + x[2:])
            elif p == "Q:":
                out.add("N:" + x[2:])
            elif p == "E:":
                out |= self._entry_whole(x[2:])
            elif x in HOLDERS:
                out |= {D, DS}
            elif x in DICTS:
                continue                        # a dict's key
            else:
                raise Unsupported("a choice from a record-derived structure (%s) at line %d" % (x, lineno))
        return out

    # -- control ----------------------------------------------------------------

    def glabel(self, fn, gid, seen=()):
        g = fn.guards[gid]
        lab = self.ev(g["expr"], fn, g["site"], ())
        if g["kind"] == "for":
            return lab
        out = _plain(lab)
        if g["kind"] == "exit":
            for o in g["outer"]:
                if o not in seen:
                    out |= _plain(self.glabel(fn, o, seen + (gid,)))
        return out

    def control(self, fn, site, names, mode):
        """The facts of every control decision in force at `site`, the
        definition of `names` there, except one that governs every use that
        definition reaches (it decides whether the value exists, never which
        value it holds). A definition that reaches a return keeps them all:
        the caller sees whichever return was taken. names None: all."""
        out = set()
        if site < 0:
            return out
        reached = None
        if names:
            reached = set()
            for n in names:
                for u in fn.uses.get(n, ()):
                    if site in fn.reaching(n, u):
                        reached.add(u)
            if reached & fn.escapes:
                reached = None
        for gid in fn.stmts[site]["guards"]:
            if reached is not None and reached <= fn.guards[gid]["governed"]:
                continue
            lab = self.glabel(fn, gid)
            out |= _cify(lab) if mode == "container" else _plain(lab)
        return out

    def _names_of(self, fn, var):
        out = {var}
        while var in fn.alias:
            var = fn.alias[var]
            out.add(var)
        return out

    # -- statements -------------------------------------------------------------

    def _process(self, fn):
        for idx, st in enumerate(fn.stmts):
            n = st["node"]
            if isinstance(n, ast.Assign):
                if (len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                        and isinstance(n.value, ast.Dict)):
                    lv = self.dict_lit(n.value, fn, idx, (), {n.targets[0].id})
                    self.assign(n.targets[0], lv, n.value, fn, idx)
                    continue
                lv = self.ev(n.value, fn, idx, ())
                for t in n.targets:
                    self.assign(t, lv, n.value, fn, idx)
            elif isinstance(n, ast.AugAssign):
                lv = self.ev(n.value, fn, idx, ())
                if isinstance(n.target, ast.Name):
                    lv = lv | self.use(n.target.id, fn, idx, ())
                    self.assign(n.target, lv, None, fn, idx)
                elif isinstance(n.target, ast.Subscript):
                    load = ast.Subscript(value=n.target.value, slice=n.target.slice, ctx=ast.Load())
                    ast.copy_location(load, n.target)
                    self.sub_assign(n.target, lv | self.ev(load, fn, idx, ()), fn, idx)
                else:
                    raise Unsupported("augmented target at line %d" % n.lineno)
            elif isinstance(n, ast.Expr):
                self.ev(n.value, fn, idx, ())
            elif isinstance(n, ast.Return):
                lab = self.ev(n.value, fn, idx, ()) if n.value is not None else set()
                self._add(self.ret, fn.key, lab | self.control(fn, idx, None, "value"))
            elif isinstance(n, ast.If):
                self.ev(n.test, fn, idx, ())
            elif isinstance(n, ast.For):
                per = self._pair_targets(n.iter, n.target, fn, idx, ())
                if per is not None:
                    for tt, lab in zip(n.target.elts, per):
                        self.assign(tt, lab, None, fn, idx)
                else:
                    it = self.ev(n.iter, fn, idx, ())
                    self.assign(n.target, self._elem(it, n.lineno), None, fn, idx)
                cs = self._iter_consts(n.iter, fn)
                if cs is not None and isinstance(n.target, ast.Name):
                    self.consts[(fn.key, n.target.id)] = cs
            elif isinstance(n, ast.Raise):
                if n.exc is not None:
                    self.ev(n.exc, fn, idx, ())
                if n.cause is not None:
                    self.ev(n.cause, fn, idx, ())

    def _pair_targets(self, it, target, fn, site, scopes):
        """enumerate(x) or zip(a, b, ...) unpacked straight into a tuple of
        names: each target gets an element of its own argument (the index of
        enumerate is a position, which reads nothing). None for any other
        form."""
        if not (isinstance(it, ast.Call) and isinstance(it.func, ast.Name)
                and it.func.id in PAIR_BUILTINS and not self._is_local(it.func.id, fn, scopes)
                and not it.keywords and isinstance(target, (ast.Tuple, ast.List))
                and not any(isinstance(a, ast.Starred) for a in it.args)):
            return None
        args = [self.ev(a, fn, site, scopes) for a in it.args]
        if it.func.id == "enumerate":
            if len(args) != 1 or len(target.elts) != 2:
                return None
            return [set(), self._elem(args[0], it.lineno)]
        if len(args) != len(target.elts):
            return None
        return [self._elem(a, it.lineno) for a in args]

    def assign(self, t, lv, value, fn, idx):
        if isinstance(t, ast.Name):
            if t.id in fn.measure_vars:
                fresh = isinstance(value, ast.Dict) and not value.keys     # an empty row, filled below
                self._need_row(fresh or ROW in lv, "measure row name %s bound to a value that is not a "
                               "measure row" % t.id, t.lineno)
            lab = lv | self.control(fn, idx, self._names_of(fn, t.id), "value")
            self._add(self.defl, (fn.key, t.id, idx), lab)
        elif isinstance(t, (ast.Tuple, ast.List)):
            if any(isinstance(e, ast.Starred) for e in t.elts):
                raise Unsupported("starred target at line %d" % t.lineno)
            if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(t.elts) \
                    and not any(isinstance(e, ast.Starred) for e in value.elts):
                for tt, vv in zip(t.elts, value.elts):
                    self.assign(tt, self.ev(vv, fn, idx, ()), vv, fn, idx)
            else:
                for tt, lab in zip(t.elts, self._unpack(lv, len(t.elts), t.lineno)):
                    self.assign(tt, lab, None, fn, idx)
        elif isinstance(t, ast.Subscript):
            self.sub_assign(t, lv, fn, idx)
        elif isinstance(t, ast.Attribute):
            if not (fn.cls and isinstance(t.value, ast.Name) and t.value.id == fn.self_name):
                raise Unsupported("attribute target at line %d" % t.lineno)
            if (fn.cls, t.attr) == COVERAGE_ATTR:
                return
            self._add(self.attr, (fn.cls, t.attr), lv | self.control(fn, idx, None, "value"))
        else:
            raise Unsupported("target at line %d" % t.lineno)

    def _measure_names(self, key, fn, scopes):
        """The measure names a subscript key can be: a constant, a name bound
        once over a constant tuple, or a concatenation with constant pieces
        (a pattern). None when the key is none of those."""
        c = _const(key)
        if isinstance(c, str):
            return {c} if c.startswith("b4.") else set()
        if isinstance(key, ast.Name):
            for sc in reversed(scopes):
                if ("const", key.id) in sc:
                    return {x for x in sc[("const", key.id)] if x in MEAS}
            cs = self.consts.get((fn.key, key.id))
            if cs is not None and len([d for d, _k in fn.defs.get(key.id, ()) if d >= 0]) == 1:
                return {x for x in cs if x in MEAS}
            return None
        if isinstance(key, ast.BinOp) and isinstance(key.op, ast.Add):
            parts = []

            def flat(n):
                if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
                    flat(n.left)
                    flat(n.right)
                else:
                    parts.append(n)
            flat(key)
            if not any(isinstance(_const(p), str) for p in parts):
                return None
            pat = "".join(re.escape(_const(p)) if isinstance(_const(p), str) else ".*" for p in parts)
            hit = {m for m in MEAS if re.fullmatch(pat, m)}
            for p in parts:
                if isinstance(_const(p), str):
                    self.pieces.add(_const(p))
            if not hit and parts and isinstance(_const(parts[0]), str) and _const(parts[0]).startswith("b4."):
                raise Unsupported("measure pattern names nothing at line %d" % key.lineno)
            return hit
        return None

    def add_def(self, name, labels, fn, lineno):
        if name not in MEAS:
            raise Unsupported("measure-like key %s at line %d" % (name, lineno))
        self._add(self.defs, name, self._content(labels, "the measure " + name, lineno))
        self.sites.setdefault(name, set()).add((fn.key, lineno))

    def sub_assign(self, t, lv, fn, idx):
        if (isinstance(t.value, ast.Attribute) and fn.cls and isinstance(t.value.value, ast.Name)
                and t.value.value.id == fn.self_name and (fn.cls, t.value.attr) == COVERAGE_ATTR):
            return
        if (isinstance(t.value, ast.Subscript) and isinstance(_const(t.value.slice), str)
                and not _const(t.value.slice).startswith("b4.") and isinstance(t.value.value, ast.Name)):
            # one entry of a dict field (c["obs"][r] += ...): the field changes
            names = self._names_of(fn, t.value.value.id)
            key = self.ev(t.slice, fn, idx, ())
            self._add(self.field, _const(t.value.slice),
                      self._dpack(lv, t.lineno) | _cify(self._key(key, t.lineno))
                      | self.control(fn, idx, names, "container"))
            return
        if not isinstance(t.value, ast.Name):
            raise Unsupported("subscript target at line %d" % t.lineno)
        v = t.value.id
        names = self._names_of(fn, v)
        meas = self._measure_names(t.slice, fn, ())
        if meas:
            self.add_def_all(meas, lv | self.control(fn, idx, names, "value"), fn, t.lineno)
            self._add(self.defl, (fn.key, v, idx), {ROW, D})       # the name now holds a measure row
            return
        c = _const(t.slice)
        if isinstance(c, str):
            self._add(self.field, c, lv | self.control(fn, idx, names, "value"))
            return
        if v in fn.measure_vars:
            raise Unsupported("unresolved key into a measure row at line %d" % t.lineno)
        if set(self.use(v, fn, idx, ())) & set(KEYED):
            raise Unsupported("unresolved key into a measure row or field dict at line %d" % t.lineno)
        key = self.ev(t.slice, fn, idx, ())
        # a list element or a dict value: either holder, so both labels
        self._add(self.defl, (fn.key, v, idx),
                  self._pack(lv, t.lineno) | self._dpack(lv, t.lineno) | _cify(self._key(key, t.lineno))
                  | self.control(fn, idx, names, "container"))

    def add_def_all(self, names, labels, fn, lineno):
        for m in names:
            self.add_def(m, labels, fn, lineno)

    # -- expressions ------------------------------------------------------------

    def use(self, name, fn, site, scopes):
        for sc in reversed(scopes):
            if name in sc:
                return sc[name]
        if name in fn.defs:
            out = set()
            for d in fn.reaching(name, site):
                out |= self.defl.get((fn.key, name, d), set())
            return out
        if name == fn.self_name:
            return {SELF}
        if name in self.fns or name in self.classes:
            raise Unsupported("the function %s used as a value in %s" % (name, fn.key))
        if hasattr(cm, name) or name in ("None", "True", "False") or name in BUILTIN_VALUES:
            return set()
        raise Unsupported("unknown name %s in %s" % (name, fn.key))

    def _is_local(self, name, fn, scopes):
        return any(name in sc for sc in scopes) or name in fn.defs or name == fn.self_name

    def _iter_consts(self, it, fn, scopes=()):
        if isinstance(it, ast.Name) and not self._is_local(it.id, fn, scopes) and hasattr(cm, it.id):
            v = getattr(cm, it.id)
            if isinstance(v, (tuple, list)) and all(isinstance(x, str) for x in v):
                return set(v)
        if isinstance(it, (ast.Tuple, ast.List)) and all(isinstance(_const(e), str) for e in it.elts):
            return {_const(e) for e in it.elts}
        return None

    # The expression kinds the analysis models, by node class; ev refuses
    # every other kind (the one place).
    EXPRS = {ast.Constant: "e_const", ast.Name: "e_name", ast.Tuple: "e_pack", ast.List: "e_pack",
             ast.Set: "e_pack", ast.Starred: "e_starred", ast.Dict: "e_dict", ast.BinOp: "e_binop",
             ast.UnaryOp: "e_unary", ast.BoolOp: "e_boolop", ast.Compare: "compare", ast.IfExp: "e_ifexp",
             ast.Call: "call", ast.Attribute: "attribute", ast.Subscript: "subscript",
             ast.ListComp: "comp", ast.SetComp: "comp", ast.GeneratorExp: "comp", ast.DictComp: "comp",
             ast.JoinedStr: "e_joined", ast.FormattedValue: "e_formatted"}

    def ev(self, node, fn, site, scopes):
        if node is None:
            return set()
        rule = self.EXPRS.get(type(node))
        if rule is None:
            raise Unsupported("no rule for the expression %s at line %d"
                              % (type(node).__name__, getattr(node, "lineno", 0)))
        return getattr(self, rule)(node, fn, site, scopes)

    def e_const(self, node, fn, site, scopes):
        return set()

    def e_name(self, node, fn, site, scopes):
        return set(self.use(node.id, fn, site, scopes))

    def e_pack(self, node, fn, site, scopes):
        out = set()
        for e in node.elts:
            if isinstance(e, ast.Starred):
                out |= self._keep("list", self.ev(e.value, fn, site, scopes), e.lineno)
            else:
                out |= self._pack(self.ev(e, fn, site, scopes), node.lineno)
        return out

    def e_starred(self, node, fn, site, scopes):
        return self.ev(node.value, fn, site, scopes)

    def e_dict(self, node, fn, site, scopes):
        return self.dict_lit(node, fn, site, scopes, None)

    def e_binop(self, node, fn, site, scopes):
        left, right = self.ev(node.left, fn, site, scopes), self.ev(node.right, fn, site, scopes)
        if isinstance(node.op, (ast.Add, ast.BitOr)):
            return left | right
        if isinstance(node.op, ast.BitAnd):
            # one bit of the incident word through its mask: the fact that
            # bit certifies, and not the rest of the word
            for mask, other in ((node.left, right), (node.right, left)):
                if (isinstance(mask, ast.Subscript) and isinstance(mask.value, ast.Name)
                        and mask.value.id == "INC" and not self._is_local("INC", fn, scopes)):
                    return self.ev(mask, fn, site, scopes) | self._content(other - {INCW}, "a mask",
                                                                           node.lineno)
        return self._content(left | right, "an operator", node.lineno)

    def e_unary(self, node, fn, site, scopes):
        lab = self.ev(node.operand, fn, site, scopes)
        if isinstance(node.op, ast.Not):
            return _plain(lab)
        return self._content(lab, "an operator", node.lineno)

    def e_boolop(self, node, fn, site, scopes):
        out = set()
        for v in node.values:
            out |= self.ev(v, fn, site, scopes)
        return out

    def e_ifexp(self, node, fn, site, scopes):
        return (_plain(self.ev(node.test, fn, site, scopes)) | self.ev(node.body, fn, site, scopes)
                | self.ev(node.orelse, fn, site, scopes))

    def e_joined(self, node, fn, site, scopes):
        out = set()
        for v in node.values:
            out |= self.ev(v, fn, site, scopes)
        return self._content(out, "a formatted string", node.lineno)

    def e_formatted(self, node, fn, site, scopes):
        return self.ev(node.value, fn, site, scopes) | self.ev(node.format_spec, fn, site, scopes)

    def dict_lit(self, node, fn, site, scopes, container):
        keys = [_const(kk) for kk in node.keys if kk is not None]
        has_meas = any(isinstance(c, str) and c.startswith("b4.") for c in keys)
        out = {ROW, D} if has_meas else ({D} if any(isinstance(c, str) for c in keys) else set())
        for kk, vv in zip(node.keys, node.values):
            lv = self.ev(vv, fn, site, scopes)
            if kk is None:
                if has_meas:
                    self._need_row(ROW in lv, "a measure row literal merging what is not a measure row",
                                   vv.lineno)
                out |= lv
                continue
            c = _const(kk)
            if isinstance(c, str):
                if c.startswith("b4."):
                    self.add_def(c, lv | self.control(fn, site, container, "value"), fn, kk.lineno)
                else:
                    self._add(self.field, c, lv)
                continue
            names = self._measure_names(kk, fn, scopes)
            if names:
                self.add_def_all(names, lv | self.control(fn, site, container, "value"), fn, kk.lineno)
                out |= {ROW, D}
            elif names is None and has_meas:
                raise Unsupported("unresolved key in a measure row literal at line %d" % kk.lineno)
            else:
                out |= self._dpack(lv, kk.lineno) | _cify(self._key(self.ev(kk, fn, site, scopes), kk.lineno))
        return out

    def compare(self, node, fn, site, scopes):
        left = node.left
        if (len(node.ops) == 1 and isinstance(node.ops[0], (ast.Is, ast.IsNot))
                and isinstance(node.comparators[0], ast.Constant) and node.comparators[0].value is None
                and isinstance(left, ast.Subscript)):
            names = self._measure_names(left.slice, fn, scopes)
            if names:
                self.drops.add((fn.key, node.lineno))
                return _plain(self.ev(left.value, fn, site, scopes))
        out = self.ev(left, fn, site, scopes)
        for c in node.comparators:
            out |= self.ev(c, fn, site, scopes)
        if all(isinstance(op, (ast.Is, ast.IsNot)) for op in node.ops):
            return _plain(out)                  # identity reads no data
        return self._content(out, "a comparison", node.lineno)

    def comp(self, node, fn, site, scopes):
        scope = {}
        scopes = scopes + (scope,)
        out = set()
        for gen in node.generators:
            if gen.is_async:
                raise Unsupported("async comprehension")
            per = self._pair_targets(gen.iter, gen.target, fn, site, scopes)
            it = self.ev(gen.iter, fn, site, scopes)
            out |= _cify(it)
            if per is not None:
                for tt, lab in zip(gen.target.elts, per):
                    self._bind_comp(tt, lab, scope)
            else:
                self._bind_comp(gen.target, self._elem(it, node.lineno), scope)
            cs = self._iter_consts(gen.iter, fn, scopes[:-1])
            if cs is not None and isinstance(gen.target, ast.Name):
                scope[("const", gen.target.id)] = cs
            for cond in gen.ifs:
                out |= _cify(self.ev(cond, fn, site, scopes))
        if isinstance(node, ast.DictComp):
            lv = self.ev(node.value, fn, site, scopes)
            names = self._measure_names(node.key, fn, scopes)
            if names:
                self.add_def_all(names, lv | out, fn, node.lineno)
                return out | {ROW, D}
            out |= _cify(self._key(self.ev(node.key, fn, site, scopes), node.lineno))
            out |= self._dpack(lv, node.lineno)
        else:
            out |= self._pack(self.ev(node.elt, fn, site, scopes), node.lineno)
        return out

    def _bind_comp(self, t, lv, scope):
        if isinstance(t, ast.Name):
            scope[t.id] = scope.get(t.id, set()) | lv
        elif isinstance(t, (ast.Tuple, ast.List)):
            if any(isinstance(e, ast.Starred) for e in t.elts):
                raise Unsupported("starred comprehension target at line %d" % t.lineno)
            for tt, lab in zip(t.elts, self._unpack(lv, len(t.elts), t.lineno)):
                self._bind_comp(tt, lab, scope)
        else:
            raise Unsupported("comprehension target at line %d" % t.lineno)

    def _string_key(self, b, key, lineno):
        if key.startswith("b4."):
            if key not in MEAS:
                raise Unsupported("measure-like key %s at line %d" % (key, lineno))
            rest = {x for x in b if x not in DICTS and x not in HOLDERS and not x.startswith("E:")}
            return {"M:" + key} | _plain(self._no_self(rest, lineno))
        out = set()
        known = False
        if "R" in b:
            if key not in REC_KEYS:
                raise Unsupported("record key %s at line %d" % (key, lineno))
            out |= REC_KEYS[key]
            known = True
        if "O" in b:
            if key not in cm.W["omit_keys"]:
                raise Unsupported("omission key %s at line %d" % (key, lineno))
            out.add("F:" + key)
            known = True
        if AGG in b:
            out |= self._agg()
            known = True
        # a field read of a dict: the field's own labels; a label of a list
        # or of a dict holding dicts reads nothing more here (a list has no
        # string key, and the field's value is what the field holds)
        # (a record, its omission counts and a window aggregate are not
        # field dicts: their keys were resolved above)
        rest = {x for x in b if x not in DICTS and x not in HOLDERS and not x.startswith("E:")}
        fieldy = bool(b & set(KEYED)) or not (b & {REC, OMIT, AGG})
        if fieldy and (key in self.field_keys or key in INPUT_KEYS):
            out |= self.field.get(key, set()) | INPUT_KEYS.get(key, set()) | _plain(self._no_self(rest, lineno))
            known = True
        if not known:
            raise Unsupported("key %s at line %d has no known source" % (key, lineno))
        return out

    def _agg(self):
        out = _plain(self.ret.get("contributions", set()))
        for k in self.contrib_keys:
            out |= _plain(self.field.get(k, set()))
        return out

    def subscript(self, node, fn, site, scopes):
        base, sl = node.value, node.slice
        if isinstance(sl, ast.Slice):
            out = set()
            for x in self.ev(base, fn, site, scopes):
                if x.startswith("E:"):
                    out |= self._entry_whole(x[2:])     # a slice of an entry moves its positions
                elif x in (REC, OMIT, AGG, SELF) or x in KEYED or x == DD:
                    raise Unsupported("slice of a record-derived structure (%s) at line %d" % (x, node.lineno))
                else:
                    out.add(x)
            for bound in (sl.lower, sl.upper, sl.step):
                out |= self._content(self.ev(bound, fn, site, scopes), "a slice bound", node.lineno)
            return out
        key = _const(sl)
        if isinstance(base, ast.Name) and not self._is_local(base.id, fn, scopes):
            if base.id == "INC":
                if key not in INC_KEYS:
                    raise Unsupported("INC key at line %d" % node.lineno)
                return set(INC_KEYS[key])
            if base.id in ("W", "CARD_WIRE"):
                if not isinstance(key, str):
                    raise Unsupported("W key at line %d" % node.lineno)
                return {"F:whole"} if key == "semantics" else set()
            if not hasattr(cm, base.id) or base.id in self.fns or base.id in self.classes:
                raise Unsupported("unknown name %s" % base.id)
            return self._key(self.ev(sl, fn, site, scopes), node.lineno)
        b = self.ev(base, fn, site, scopes)
        if isinstance(key, str):
            return self._string_key(b, key, node.lineno)
        if isinstance(key, int):
            return self._index(b, key, node.lineno)
        names = self._measure_names(sl, fn, scopes)
        if names:
            rest = {x for x in b if x not in DICTS and x not in HOLDERS and not x.startswith("E:")}
            return {"M:" + m for m in names} | _plain(self._no_self(rest, node.lineno))
        return self._index(b, None, node.lineno) | self._key(self.ev(sl, fn, site, scopes), node.lineno)

    def _receiver(self, b, what, lineno):
        bad = sorted(x for x in b if x in DICTS or x in HOLDERS or x[:2] in ("C:", "E:"))
        if bad:
            raise Unsupported("%s of a record-derived value (%s) at line %d" % (what, ",".join(bad), lineno))

    def attribute(self, node, fn, site, scopes):
        if isinstance(node.value, ast.Name) and node.value.id in MODULES \
                and not self._is_local(node.value.id, fn, scopes):
            raise Unsupported("module attribute %s.%s used as a value at line %d"
                              % (node.value.id, node.attr, node.lineno))
        a = node.attr
        if fn.cls and isinstance(node.value, ast.Name) and node.value.id == fn.self_name:
            if a in self.cls_attrs[fn.cls]:
                return set(self.attr.get((fn.cls, a), set()))
            raise Unsupported("attribute %s of %s" % (a, fn.cls))
        self._receiver(self.ev(node.value, fn, site, scopes), "attribute " + a, node.lineno)
        owners = [c for c, attrs in self.cls_attrs.items() if a in attrs]
        if owners:
            out = set()
            for c in owners:
                out |= self.attr.get((c, a), set())
            return out
        raise Unsupported("attribute %s at line %d" % (a, node.lineno))

    def call(self, node, fn, site, scopes):
        f = node.func
        ln = node.lineno
        if isinstance(f, ast.Name) and not self._is_local(f.id, fn, scopes):
            n = f.id
            if n in GATE:
                self.gate_calls.add(fn.key)
                if n == "_gate":
                    if not node.args:
                        raise Unsupported("gate form at line %d" % ln)
                    self._need_row(ROW in self.ev(node.args[0], fn, site, scopes),
                                   "the gate applied to what is not a measure row", ln)
                return set()
            if n in self.fns and not isinstance(self.fns[n], tuple):
                self._bind(n, node, fn, site, scopes)
                return set(self.ret.get(n, set()))
            if n in self.classes:
                self._bind(n + ".__init__", node, fn, site, scopes)
                return set()
            if n not in BUILTIN_VALUES and n != "Refusal":
                raise Unsupported("call of %s at line %d" % (n, ln))
            if n == DICT_BUILTIN:
                return self._dict_call(node, fn, site, scopes)
            if n in PAIR_BUILTINS:
                args = [self.ev(a, fn, site, scopes) for a in node.args]
                if node.keywords or any("C:hd" in a or "E:hd" in a for a in args):
                    raise Unsupported("%s over hand entries at line %d" % (n, ln))
                return self._keep("list", set().union(*args) if args else set(), ln)
            allv = set()
            for a in node.args:
                allv |= self.ev(a, fn, site, scopes)
            for kw in node.keywords:
                if kw.arg is None or (kw.arg == "key" and not (isinstance(kw.value, ast.Name)
                                                               and kw.value.id in BUILTIN_VALUES)):
                    raise Unsupported("keyword of %s at line %d" % (n, ln))
                allv |= self.ev(kw.value, fn, site, scopes)
            if n in TRUTH_BUILTINS:
                return _plain(allv)
            if n in CONTENT_BUILTINS or n == "Refusal":
                return self._content(allv, n, ln)
            if n in PICK_BUILTINS:
                if n == "next":                 # the first element: no element is compared
                    return self._pick(allv, ln)
                return self._pick(allv, ln) | self._content(self._elem(self._keep(n, allv, ln), ln), n, ln)
            kept = self._keep(n, allv, ln)
            if n == "sorted":
                kept |= self._content(self._elem(kept, ln), n, ln)    # the order reads each element
            return kept
        if not isinstance(f, ast.Attribute):
            raise Unsupported("call form at line %d" % ln)
        m = f.attr
        if isinstance(f.value, ast.Name) and f.value.id in MODULES and not self._is_local(f.value.id, fn, scopes):
            if (f.value.id, m) not in MODULE_CALLS:
                raise Unsupported("module call %s.%s at line %d" % (f.value.id, m, ln))
            out = set()
            for a in node.args:
                out |= self.ev(a, fn, site, scopes)
            for kw in node.keywords:
                out |= self.ev(kw.value, fn, site, scopes)
            return self._content(out, "%s.%s" % (f.value.id, m), ln)
        b = self.ev(f.value, fn, site, scopes)
        if m in self.methods:
            self._receiver(b, "method " + m, ln)
            out = set()
            for key in self.methods[m]:
                self._bind(key, node, fn, site, scopes)
                out |= self.ret.get(key, set())
            return out
        args = [self.ev(a, fn, site, scopes) for a in node.args]
        for kw in node.keywords:
            args.append(self.ev(kw.value, fn, site, scopes))
        allargs = set().union(*args) if args else set()
        if m in MUTATORS:
            return self._mutate(node, f, m, b, args, allargs, fn, site)
        if m == "get":
            if not node.args or len(node.args) > 2 or node.keywords:
                raise Unsupported("get form at line %d" % ln)
            c = _const(node.args[0])
            default = args[1] if len(args) > 1 else set()
            if isinstance(c, str):
                return self._string_key(b, c, ln) | default
            names = self._measure_names(node.args[0], fn, scopes)
            if names:
                rest = {x for x in b if x not in DICTS and x not in HOLDERS and not x.startswith("E:")}
                return {"M:" + mm for mm in names} | _plain(self._no_self(rest, ln)) | default
            return self._index(b, None, ln) | self._key(args[0], ln) | default
        if m in KEEP_METHODS:
            if args:
                raise Unsupported("arguments of %s at line %d" % (m, ln))
            if m == "copy":
                return b
            if m == "keys":
                return {x for x in b if x not in DICTS}
            bad = sorted(x for x in b if x in (REC, OMIT, AGG, SELF) or x in KEYED)
            if bad:
                raise Unsupported("method %s of a record-derived structure (%s) at line %d"
                                  % (m, ",".join(bad), ln))
            return {DS if x == DD else x for x in b}
        if m in SCALAR_METHODS:
            return self._content(b | allargs, "method " + m, ln)
        raise Unsupported("method %s at line %d" % (m, ln))

    def _dict_call(self, node, fn, site, scopes):
        parts = [self.ev(a, fn, site, scopes) for a in node.args]
        parts += [self.ev(kw.value, fn, site, scopes) for kw in node.keywords if kw.arg is None]
        named = [kw for kw in node.keywords if kw.arg is not None]
        if any(ROW in p for p in parts):
            if named:
                raise Unsupported("a measure row merged with named fields at line %d" % node.lineno)
            self._need_row(all(ROW in p for p in parts), "a measure row merged with what is not a measure row",
                           node.lineno)
            return set().union(*parts)
        out = set().union(*parts) if parts else set()
        for kw in named:
            out |= self._dpack(self.ev(kw.value, fn, site, scopes), node.lineno)
        return out

    def _mutate(self, node, f, m, b, args, allargs, fn, site):
        ln = node.lineno
        if not isinstance(f.value, ast.Name):
            raise Unsupported("mutation of a non-name at line %d" % ln)
        v = f.value.id
        if b & {REC, OMIT, AGG, SELF}:
            raise Unsupported("mutation of a record-derived structure at line %d" % ln)
        if v in fn.measure_vars or ROW in b:
            if m != "update" or len(args) != 1 or node.keywords:
                raise Unsupported("mutation of a measure row at line %d" % ln)
            self._need_row(ROW in args[0], "a measure row merged with what is not a measure row", ln)
            # merging a measure row built here: its measures are defined there
            return set()
        if self.strict and m == "update" and any(ROW in a or D in a for a in args):
            raise Unsupported("a dict merged with a measure row or field dict at line %d" % ln)
        if m == "setdefault":
            if not args or len(args) > 2:
                raise Unsupported("setdefault form at line %d" % ln)
            add = _cify(self._key(args[0], ln)) | (self._dpack(args[1], ln) if len(args) > 1 else set())
        elif m in ("append", "add"):
            add = self._pack(allargs, ln)
        elif m == "insert":
            if len(args) != 2:
                raise Unsupported("insert form at line %d" % ln)
            add = self._content(args[0], "a position", ln) | self._pack(args[1], ln)
        else:                                   # extend, update: the argument's elements
            add = self._keep("list", allargs, ln)
        ctl = self.control(fn, site, self._names_of(fn, v), "container")
        self._add(self.defl, (fn.key, v, site), add | ctl)
        if m == "setdefault":
            return self._index(b | add, None, ln) | (args[1] if len(args) > 1 else set())
        return set()

    # -- results ----------------------------------------------------------------

    def _check(self):
        missing = sorted(MEAS - set(self.sites))
        if missing:
            raise Unsupported("measures with no definition: %s" % missing)
        for key, v in self.fns.items():
            node = v[1] if isinstance(v, tuple) else v
            writes = any(isinstance(_const(n), str) and _const(n) in MEAS for n in ast.walk(node))
            if writes and key not in self.reach and key not in GATE:
                raise Unsupported("%s names a measure and is not reachable" % key)
        for key in self.reach:
            for n in ast.walk(self._fn(key).node):
                c = _const(n)
                if isinstance(c, str) and c.startswith("b4.") and c not in MEAS and c not in self.pieces:
                    raise Unsupported("measure-like string %r in %s" % (c, key))
        if ROW not in self.ret.get("window_row", set()):
            raise Unsupported("window_row returns what is not a measure row")

    def read(self, name, seen=None):
        seen = set() if seen is None else seen
        if name in seen:
            return set()
        seen.add(name)
        out = set()
        for x in self.defs.get(name, ()):
            if x.startswith("M:"):
                out |= self.read(x[2:], seen)
            elif x[:2] in ("F:", "C:"):
                out.add(x[2:])
        return out

    def statements(self):
        """The measures whose value carries the incident word read whole
        (the record's coverage statement, excluded from READ like ok)."""
        def carries(name, seen):
            if name in seen:
                return False
            seen.add(name)
            ds = self.defs.get(name, ())
            return STATEMENT in ds or any(carries(x[2:], seen) for x in ds if x.startswith("M:"))
        return sorted(m for m in MEAS if carries(m, set()))

    def reads(self):
        out = {}
        for name in sorted(MEAS):
            facts = self.read(name)
            if not facts <= set(FACTS):
                raise Unsupported("unknown fact in %s: %s" % (name, sorted(facts - set(FACTS))))
            out[name] = frozenset(facts)
        return out


def analyze(source=None):
    a = Analysis(source).run()
    return a, a.reads()


def counts(reads, needs):
    """The proof's counts: measures, (measure, fact) pairs read, declared,
    their union (the generated one-at-a-time omission cases), and read but
    not declared."""
    read_pairs = {(m, f) for m, fs in reads.items() for f in fs}
    need_pairs = {(m, f) for m, fs in needs.items() for f in fs}
    return {"measures": len(reads), "read_pairs": len(read_pairs), "declared_pairs": len(need_pairs),
            "omission_cases": len(read_pairs | need_pairs), "undeclared": len(read_pairs - need_pairs)}


if __name__ == "__main__":
    unsupported = 0
    try:
        a, r = analyze()
    except Unsupported as exc:
        print("card read sets: Unsupported over the real tree: %s" % exc)
        print("counts: Unsupported raised 1, measures analysed 0")
        sys.exit(1)
    print("card read sets: %d functions analysed, gate calls in %s, NOT-RUN tests at %s"
          % (len(a.reach), sorted(a.gate_calls), sorted(a.drops)))
    for subject, names in cm.MEASURES.items():
        for name in names:
            extra = sorted(r[name] - set(cm.NEEDS[name]))
            print("%-28s READ %-40s DECLARED %-50s %s" % (
                name, ",".join(sorted(r[name])) or "-", ",".join(cm.NEEDS[name]) or "-",
                ("UNDECLARED " + ",".join(extra)) if extra else "ok"))
    print("counts: %s, Unsupported raised %d" % (counts(r, cm.NEEDS), unsupported))
