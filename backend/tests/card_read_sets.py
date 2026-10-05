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
    per-entry field read alone does not depend on the list's fact;
  - a hand entry's slot list and spawn list (positions sl and sp of an hd
    entry) are read at all: any read of either depends on sl / sp;
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
covered, which enforce NEEDS), the record's coverage statement (the ok
dict, which only the gate and the coverage counters read), and a test of
whether a measure IS None (its NOT-RUN state, the gate's output, which the
not-run counters count); `drops` lists every place that last exclusion
applied."""

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
PLAIN_BUILTINS = {"len", "sum", "any", "all", "min", "max", "abs", "int", "bool", "str", "float",
                  "divmod", "round", "next", "isinstance", "hash", "repr", "ord", "chr", "range"}
KEEP_BUILTINS = {"sorted", "list", "set", "tuple", "frozenset", "reversed", "enumerate", "zip",
                 "dict", "iter"}
MUTATORS = {"append", "add", "extend", "update", "insert", "setdefault"}
KEEP_METHODS = {"items", "values", "keys", "copy"}
MEAS = {n for names in cm.MEASURES.values() for n in names}
FACTS = tuple(cm.COVER)
LISTS = ("cards", "held0", "ph", "hd", "ap")
# where a stored record's top-level keys lead: a fact-certified list, the
# first-phase order, the omission counts, or data no fact covers
REC_KEYS = {key: set() for key in cm.W["keys"]}
REC_KEYS.update({key: {"C:" + key} for key in LISTS})
REC_KEYS.update({"po": {"F:first"}, "omit": {"O"}})
INC_KEYS = {"lost": {"F:whole"}, "fault": {"F:whole"}, "first": {"F:first"},
            "all": {"F:whole", "F:first"}}
INPUT_KEYS = {"rec": {"R"}, "seat": set(), "other": set(), "conflict": set()}
AGG = "AGG"


class Unsupported(Exception):
    """A construct the analysis has no rule for: refused, never read as
    nothing."""


def _plain(ls):
    out = set()
    for x in ls:
        if x.startswith("C:"):
            out.add("F:" + x[2:])
        elif x.startswith("F:") or x.startswith("M:"):
            out.add(x)
    return out


def _elem(ls):
    out = set()
    for x in ls:
        if x.startswith("C:"):
            out.add("E:" + x[2:])
        elif x.startswith("F:") or x.startswith("M:"):
            out.add(x)
    return out


def _cify(ls):
    return {("C:" + x[2:]) if x.startswith("F:") else x for x in _plain(ls)}


def _untag(ls):
    return {x for x in ls if x[:2] in ("F:", "C:", "M:")}


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


class Fn:
    """One function: its statements in walk order with the control decisions
    in force at each, and every definition and use of each variable."""

    def __init__(self, key, node, cls=None):
        self.key, self.node, self.cls = key, node, cls
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
            elif not isinstance(st, (ast.Assign, ast.AugAssign, ast.Expr, ast.Return, ast.Continue,
                                     ast.Pass, ast.Raise)):
                raise Unsupported("%s at line %d" % (type(st).__name__, st.lineno))

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
            if isinstance(node, ast.FunctionDef):
                self.fns[node.name] = node
            elif isinstance(node, ast.ClassDef):
                self.classes[node.name] = node
                self.cls_attrs[node.name] = set()
                for m in node.body:
                    if isinstance(m, ast.FunctionDef):
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
        while True:
            before = self._size()
            self._add(self.defl, ("contributions", "view", -1), self.ret.get("card_view", set()))
            self._add(self.defl, ("window_row", "agg", -1), {AGG})
            for key in sorted(self.reach):
                self._process(self._fn(key))
            if self._size() == before:
                break
        self._check()
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
                    self.assign(n.targets[0], lv, None, fn, idx)
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
                it = self.ev(n.iter, fn, idx, ())
                self.assign(n.target, _elem(it), None, fn, idx)
                cs = self._iter_consts(n.iter, fn)
                if cs is not None and isinstance(n.target, ast.Name):
                    self.consts[(fn.key, n.target.id)] = cs
            elif isinstance(n, ast.Raise):
                if n.exc is not None:
                    self.ev(n.exc, fn, idx, ())

    def assign(self, t, lv, value, fn, idx):
        if isinstance(t, ast.Name):
            lab = lv | self.control(fn, idx, self._names_of(fn, t.id), "value")
            self._add(self.defl, (fn.key, t.id, idx), lab)
        elif isinstance(t, (ast.Tuple, ast.List)):
            if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(t.elts):
                for tt, vv in zip(t.elts, value.elts):
                    self.assign(tt, self.ev(vv, fn, idx, ()), None, fn, idx)
            elif "E:hd" in lv and len(t.elts) == cm.WIDTH["hd"]:
                base = _untag(lv)
                for i, tt in enumerate(t.elts):
                    self.assign(tt, base | ({self.positions[i]} if i in self.positions else set()),
                                None, fn, idx)
            else:
                for tt in t.elts:
                    self.assign(tt, _untag(lv), None, fn, idx)
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
        over a constant tuple, or a concatenation with constant pieces (a
        pattern). None when the key is none of those."""
        c = _const(key)
        if isinstance(c, str):
            return {c} if c.startswith("b4.") else set()
        if isinstance(key, ast.Name):
            for sc in reversed(scopes):
                if ("const", key.id) in sc:
                    return {x for x in sc[("const", key.id)] if x in MEAS}
            cs = self.consts.get((fn.key, key.id))
            if cs is not None:
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
            pat = "".join(re.escape(_const(p)) if isinstance(_const(p), str) else ".+" for p in parts)
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
        self._add(self.defs, name, labels)
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
                      lv | _cify(key) | self.control(fn, idx, names, "container"))
            return
        if not isinstance(t.value, ast.Name):
            raise Unsupported("subscript target at line %d" % t.lineno)
        v = t.value.id
        names = self._names_of(fn, v)
        meas = self._measure_names(t.slice, fn, ())
        if meas:
            self.add_def_all(meas, lv | self.control(fn, idx, names, "value"), fn, t.lineno)
            return
        c = _const(t.slice)
        if isinstance(c, str):
            self._add(self.field, c, lv | self.control(fn, idx, names, "value"))
            return
        if v in fn.measure_vars:
            raise Unsupported("unresolved key into a measure row at line %d" % t.lineno)
        key = self.ev(t.slice, fn, idx, ())
        self._add(self.defl, (fn.key, v, idx), lv | _cify(key) | self.control(fn, idx, names, "container"))

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
            return {"SELF"}
        if hasattr(cm, name) or name in ("None", "True", "False") or name in PLAIN_BUILTINS | KEEP_BUILTINS:
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

    def ev(self, node, fn, site, scopes):
        if node is None or isinstance(node, ast.Constant):
            return set()
        if isinstance(node, ast.Name):
            return set(self.use(node.id, fn, site, scopes))
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            out = set()
            for e in node.elts:
                out |= self.ev(e, fn, site, scopes)
            return out
        if isinstance(node, ast.Starred):
            return self.ev(node.value, fn, site, scopes)
        if isinstance(node, ast.Dict):
            return self.dict_lit(node, fn, site, scopes, None)
        if isinstance(node, ast.BinOp):
            lab = self.ev(node.left, fn, site, scopes) | self.ev(node.right, fn, site, scopes)
            return lab if isinstance(node.op, (ast.Add, ast.BitOr)) else _plain(lab)
        if isinstance(node, ast.UnaryOp):
            return _plain(self.ev(node.operand, fn, site, scopes))
        if isinstance(node, ast.BoolOp):
            out = set()
            for v in node.values:
                out |= self.ev(v, fn, site, scopes)
            return _plain(out)
        if isinstance(node, ast.Compare):
            return self.compare(node, fn, site, scopes)
        if isinstance(node, ast.IfExp):
            return (_plain(self.ev(node.test, fn, site, scopes)) | self.ev(node.body, fn, site, scopes)
                    | self.ev(node.orelse, fn, site, scopes))
        if isinstance(node, ast.Call):
            return self.call(node, fn, site, scopes)
        if isinstance(node, ast.Attribute):
            return self.attribute(node, fn, site, scopes)
        if isinstance(node, ast.Subscript):
            return self.subscript(node, fn, site, scopes)
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            return self.comp(node, fn, site, scopes)
        if isinstance(node, ast.JoinedStr):
            out = set()
            for v in node.values:
                out |= self.ev(v, fn, site, scopes)
            return _plain(out)
        if isinstance(node, ast.FormattedValue):
            return self.ev(node.value, fn, site, scopes)
        raise Unsupported("%s at line %d" % (type(node).__name__, getattr(node, "lineno", 0)))

    def dict_lit(self, node, fn, site, scopes, container):
        out = set()
        for kk, vv in zip(node.keys, node.values):
            lv = self.ev(vv, fn, site, scopes)
            if kk is None:
                out |= lv
                continue
            c = _const(kk)
            if isinstance(c, str):
                if c.startswith("b4."):
                    self.add_def(c, lv | self.control(fn, site, container, "value"), fn, kk.lineno)
                else:
                    self._add(self.field, c, lv)
            else:
                out |= lv | _cify(self.ev(kk, fn, site, scopes))
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
        return _plain(out)

    def comp(self, node, fn, site, scopes):
        scope = {}
        scopes = scopes + (scope,)
        out = set()
        for gen in node.generators:
            if gen.is_async:
                raise Unsupported("async comprehension")
            it = self.ev(gen.iter, fn, site, scopes)
            out |= it
            self._bind_comp(gen.target, _elem(it), scope)
            cs = self._iter_consts(gen.iter, fn, scopes[:-1])
            if cs is not None and isinstance(gen.target, ast.Name):
                scope[("const", gen.target.id)] = cs
            for cond in gen.ifs:
                out |= _cify(self.ev(cond, fn, site, scopes))
        if isinstance(node, ast.DictComp):
            out |= self.ev(node.key, fn, site, scopes) | self.ev(node.value, fn, site, scopes)
        else:
            out |= self.ev(node.elt, fn, site, scopes)
        return out

    def _bind_comp(self, t, lv, scope):
        if isinstance(t, ast.Name):
            scope[t.id] = scope.get(t.id, set()) | lv
        elif isinstance(t, (ast.Tuple, ast.List)):
            if "E:hd" in lv and len(t.elts) == cm.WIDTH["hd"]:
                for i, tt in enumerate(t.elts):
                    self._bind_comp(tt, _untag(lv) | ({self.positions[i]} if i in self.positions else set()),
                                    scope)
            else:
                for tt in t.elts:
                    self._bind_comp(tt, _untag(lv), scope)
        else:
            raise Unsupported("comprehension target at line %d" % t.lineno)

    def _string_key(self, b, key, lineno):
        if key.startswith("b4."):
            if key not in MEAS:
                raise Unsupported("measure-like key %s at line %d" % (key, lineno))
            return {"M:" + key} | _plain(b)
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
        rest = b - {"R", "O", AGG}
        if key in self.field_keys or key in INPUT_KEYS:
            out |= self.field.get(key, set()) | INPUT_KEYS.get(key, set()) | _plain(rest)
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
            return (self.ev(base, fn, site, scopes) | _plain(self.ev(sl.lower, fn, site, scopes))
                    | _plain(self.ev(sl.upper, fn, site, scopes)) | _plain(self.ev(sl.step, fn, site, scopes)))
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
            if not hasattr(cm, base.id):
                raise Unsupported("unknown name %s" % base.id)
            return _plain(self.ev(sl, fn, site, scopes))
        b = self.ev(base, fn, site, scopes)
        if isinstance(key, str):
            return self._string_key(b, key, node.lineno)
        if isinstance(key, int):
            if "R" in b or "O" in b:
                raise Unsupported("positional read of the record at line %d" % node.lineno)
            if "E:hd" in b:
                return _untag(b) | ({self.positions[key]} if key in self.positions else set())
            return set(b)
        names = self._measure_names(sl, fn, scopes)
        if names:
            return {"M:" + m for m in names} | _plain(b)
        if "R" in b:
            raise Unsupported("computed record key at line %d" % node.lineno)
        if "O" in b:
            return {"F:" + x for x in cm.W["omit_keys"]}
        return _plain(b) | _plain(self.ev(sl, fn, site, scopes))

    def attribute(self, node, fn, site, scopes):
        if isinstance(node.value, ast.Name) and node.value.id in MODULES:
            return set()
        a = node.attr
        if fn.cls and isinstance(node.value, ast.Name) and node.value.id == fn.self_name:
            if a in self.cls_attrs[fn.cls]:
                return set(self.attr.get((fn.cls, a), set()))
            if a in self.methods:
                return set()
            raise Unsupported("attribute %s of %s" % (a, fn.cls))
        self.ev(node.value, fn, site, scopes)
        owners = [c for c, attrs in self.cls_attrs.items() if a in attrs]
        if owners:
            out = set()
            for c in owners:
                out |= self.attr.get((c, a), set())
            return out
        if a in self.methods:
            return set()
        raise Unsupported("attribute %s at line %d" % (a, node.lineno))

    def call(self, node, fn, site, scopes):
        f = node.func
        if isinstance(f, ast.Name) and not self._is_local(f.id, fn, scopes):
            n = f.id
            if n in GATE:
                self.gate_calls.add(fn.key)
                return set()
            args = set()
            for a in node.args:
                args |= self.ev(a, fn, site, scopes)
            for kw in node.keywords:
                args |= self.ev(kw.value, fn, site, scopes)
            if n in PLAIN_BUILTINS:
                return _plain(args)
            if n in KEEP_BUILTINS:
                return args
            if n in self.fns and not isinstance(self.fns[n], tuple):
                self._bind(n, node, fn, site, scopes)
                return set(self.ret.get(n, set()))
            if n in self.classes:
                self._bind(n + ".__init__", node, fn, site, scopes)
                return set()
            if n == "type" or n == "Refusal":
                return _plain(args)
            raise Unsupported("call of %s at line %d" % (n, node.lineno))
        if not isinstance(f, ast.Attribute):
            raise Unsupported("call form at line %d" % node.lineno)
        m = f.attr
        if isinstance(f.value, ast.Name) and f.value.id in MODULES:
            out = set()
            for a in node.args:
                out |= self.ev(a, fn, site, scopes)
            return _plain(out)
        if m in self.methods:
            out = set()
            self.ev(f.value, fn, site, scopes)
            for key in self.methods[m]:
                self._bind(key, node, fn, site, scopes)
                out |= self.ret.get(key, set())
            return out
        b = self.ev(f.value, fn, site, scopes)
        args = [self.ev(a, fn, site, scopes) for a in node.args]
        for kw in node.keywords:
            args.append(self.ev(kw.value, fn, site, scopes))
        allargs = set().union(*args) if args else set()
        if m in MUTATORS:
            if not isinstance(f.value, ast.Name):
                raise Unsupported("mutation of a non-name at line %d" % node.lineno)
            v = f.value.id
            if v in fn.measure_vars and m != "update":
                raise Unsupported("mutation of a measure row at line %d" % node.lineno)
            if v in fn.measure_vars and m == "update":
                # merging a callee's measure dict: its measures are defined there
                return set()
            if m == "setdefault":
                add = _cify(args[0]) | (args[1] if len(args) > 1 else set())
            else:
                add = allargs
            ctl = self.control(fn, site, self._names_of(fn, v), "container")
            self._add(self.defl, (fn.key, v, site), add | ctl)
            return (b | allargs) if m == "setdefault" else set()
        if m == "get":
            c = _const(node.args[0]) if node.args else None
            default = args[1] if len(args) > 1 else set()
            if isinstance(c, str):
                return self._string_key(b, c, node.lineno) | default
            return _plain(b) | _plain(args[0] if args else set()) | default
        if m in KEEP_METHODS:
            return b
        return _plain(b | allargs)

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
    a, r = analyze()
    print("card read sets: %d functions analysed, gate calls in %s, NOT-RUN tests at %s"
          % (len(a.reach), sorted(a.gate_calls), sorted(a.drops)))
    for subject, names in cm.MEASURES.items():
        for name in names:
            extra = sorted(r[name] - set(cm.NEEDS[name]))
            print("%-28s READ %-40s DECLARED %-50s %s" % (
                name, ",".join(sorted(r[name])) or "-", ",".join(cm.NEEDS[name]) or "-",
                ("UNDECLARED " + ",".join(extra)) if extra else "ok"))
    print("counts: %s" % counts(r, cm.NEEDS))
