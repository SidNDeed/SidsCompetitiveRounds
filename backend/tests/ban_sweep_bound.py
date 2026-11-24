"""The ban census's statement-text resolver over its closed failures (RULING-CENSUS-3 section 8,
RULING-CENSUS-4, RULING-CENSUS-5): each place the census cannot read whole is READ, EXPANDED (exact texts),
BOUNDED (bare holes bounded by their reaching sets, conditions i to iv), JUDGED (an exact value whose
closure is not closed, pinned by the integrator), or REMAINING by cause.

The forms: the loop texts (ORDER 2), typed holes, DICT_PARTS with the alias, EXPANSION of a display's whole
values, PARAM through every call of a function (holes and whole arguments), MUTATION (a store into a
container is a binding of it), and VALUE (a module-level value read from one child process that imports the
read modules). Run it with runpy.run_path(path, init_globals={"_BOUND_IN": {...}}): keys srcs (module ->
source text; main may be a mutant, read by mdpl_census through main_text), values (the child's answers),
collect (True: gather the child's requests instead). The namespace returned holds rows, VALUE_REQ,
VALUE_WHY and METHOD_CALLS. Tests alone; it never imports a product module itself."""
import ast
import hashlib
import itertools
import json
import os
import re
import sys
from collections import Counter, defaultdict

_IN = globals().get("_BOUND_IN") or {}
T = os.path.dirname(os.path.abspath(__file__))
if T not in sys.path:
    sys.path.insert(0, T)
sys.setrecursionlimit(30000)
import ban_sweep_census as B  # noqa: E402
import ban_sweep_locks as L  # noqa: E402
import mdpl_census as mc  # noqa: E402
from ban_sweep_tables import TABLE_CLASSES  # noqa: E402

if _IN.get("srcs"):
    srcs = dict(_IN["srcs"])
else:
    srcs = {}
    for f in sorted(os.listdir(B.API)):
        if f.endswith(".py"):
            with open(os.path.join(B.API, f), encoding="utf-8") as fh:
                srcs[f[:-3]] = fh.read()
fails = B.statement_text_failures(srcs)
trees = {m: ast.parse(s) for m, s in srcs.items()}

# ---------------------------------------------------------------- the reader, with hole identity
HOLES = {}                      # n -> (expr node, function name or None, module)
MK = re.compile(r"\{\?\}\x01(\d+)\x02")
_orig = mc.Source.text


def _mark(self, node):
    n = len(HOLES)
    HOLES[n] = (node, self._fn_stack[-1] if self._fn_stack else None, self._cur)
    return "{?}\x01%d\x02" % n


def text(self, x, local, plain=False):
    if isinstance(x, ast.JoinedStr):
        out = []
        for v in x.values:
            if isinstance(v, ast.Constant):
                out.append(str(v.value))
            elif isinstance(v, ast.FormattedValue):
                t = self.text(v.value, local)
                out.append(t if t is not None else _mark(self, v.value))
        r = "".join(out)
    elif isinstance(x, ast.BinOp) and isinstance(x.op, ast.Add):
        a, b = self.text(x.left, local), self.text(x.right, local)
        r = None if a is None and b is None else \
            (a if a is not None else _mark(self, x.left)) + (b if b is not None else _mark(self, x.right))
    elif isinstance(x, ast.BinOp) and isinstance(x.op, ast.Mod):
        a = self.text(x.left, local)
        r = None if a is None else re.sub(r"%(?:\(\w+\))?s", lambda _m: _mark(self, x.right), a)
    elif isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and x.func.attr in ("format", "strip"):
        a = self.text(x.func.value, local)
        args = ast.Tuple(elts=list(x.args) + [k.value for k in x.keywords], ctx=ast.Load())
        r = None if a is None else re.sub(r"\{\w*\}", lambda _m: _mark(self, args), a)
    else:
        r = _orig(self, x, local, plain)
    if hasattr(x, "lineno"):
        REC[(self._cur, x.lineno, x.col_offset)].append(r)
    return r


REC = defaultdict(list)
mc.Source.text = text
src = mc.Source(main_text=srcs["main"])
# RULING-CENSUS-8 (a): one parse. The reader parsed these modules itself; the resolver takes the reader's
# trees, so a node or def the reader hands over is the node the resolver's indexes are keyed by.
for _m, _tr in src.trees.items():
    _given = srcs.get(_m)
    if _m != "main":
        with open(os.path.join(mc.API, _m + ".py"), encoding="utf-8") as _fh:
            _disk = _fh.read()
        if _given != _disk:
            raise RuntimeError("the reader parsed %s.py from a text the resolver was not given" % _m)
    trees[_m] = _tr
del _m, _tr, _given
mc.census(src)
names = set(src.defs) | set(getattr(src, "qdefs", {}))
FN_NAME = {}
DICTS = defaultdict(set)
for sp in src._ns.values():
    for k, v in sp["dicts"].items():
        DICTS[k] |= set(v)

for _k in names:
    _n = (src.qdefs.get(_k) if hasattr(src, 'qdefs') else None) or src.defs.get(_k)
    if _n is not None:
        FN_NAME.setdefault(id(_n), _k)

# ---------------------------------------------------------------- the verdict functions and their lock words
VERDICT_RX = [("row_locks_before_the_gate", B._ROW_LOCK_SQL), ("_write_call", B._WRITE_SQL),
              ("identity_lock_failures", B._ADVISORY), ("identity_lock_failures", B._IDENTITY_KEY),
              ("shared_and_exclusive_failures", B._EXCLUSIVE_KEY),
              ("ban_writers_without_the_lock", B._IDENTITY_LOCK_SQL),
              ("ban_sweep_locks.is_taking_statement", L.IDENTITY_KEY)]
# A lock word: the first word of each alternative of a verdict pattern, and the
# identity key's own marker (hashtext). Derived from the patterns themselves.
LOCK_WORDS = {}


def top_alternatives(pat):
    """The pattern's alternatives at depth 0 (escaped parentheses do not count); a single
    group around the whole pattern is opened first."""
    def split(s):
        out, depth, cur, i = [], 0, "", 0
        while i < len(s):
            ch = s[i]
            if ch == "\\":
                cur += s[i:i + 2]
                i += 2
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "|" and depth == 0:
                out.append(cur)
                cur = ""
            else:
                cur += ch
            i += 1
        return out + [cur]
    alts = split(pat)
    if len(alts) == 1 and pat.startswith(r"\b(") and pat.endswith(r")\b"):
        alts = split(pat[3:-3])
    return alts


for fn_name, rx in VERDICT_RX:
    for alt in top_alternatives(rx.pattern):
        w = re.search(r"[A-Za-z_]{3,}", alt.replace(r"\b", " ").replace(r"\s", " "))
        if w:
            LOCK_WORDS.setdefault(w.group(0).upper(), fn_name)
    if "hashtext" in rx.pattern:
        LOCK_WORDS.setdefault("HASHTEXT", fn_name)
LOCK_RX = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(sorted(LOCK_WORDS)) + r")(?![A-Za-z0-9_])", re.I)
TABLE_WORDS = sorted(TABLE_CLASSES)
if not LOCK_WORDS or not TABLE_WORDS:          # RULING-CENSUS-8 (b): an empty word table reads nothing
    raise RuntimeError("an empty word table: lock words %d, table words %d" % (len(LOCK_WORDS), len(TABLE_WORDS)))
DICT_PARTS = EXPANSION = PARAM = MUTATION = VALUE = True
for _sw, _on in (_IN.get("switches") or {}).items():   # a test may run one form alone
    assert _sw in ("DICT_PARTS", "EXPANSION", "PARAM", "MUTATION", "VALUE"), _sw
    globals()[_sw] = bool(_on)
VALUE_COLLECT = bool(_IN.get("collect"))
VALUES = _IN.get("values") or {}
VALUE_REQ = {}
_JUDGED_USE = []
OPEN_MUTATION = "a container changed by a call the form does not read"
_MUT_METHODS = ("append", "extend", "insert", "update", "setdefault", "add", "appendleft", "extendleft")
_PURE = {"len", "list", "tuple", "sorted", "set", "frozenset", "str", "repr", "any", "all", "min", "max", "sum",
         "enumerate", "zip", "reversed", "iter", "isinstance", "bool", "int", "dict", "text", "next", "hash",
         "id", "type", "format", "print", "getattr", "hasattr"}
_STRICT = [0]          # > 0: DICT_PARTS falls back to the strict rule (condition (c))
TABLE_RX = {t: re.compile(r"(?<![a-z_0-9])" + re.escape(t) + r"(?![a-z_0-9])") for t in TABLE_WORDS}


def verdicts(t):
    return tuple(bool(rx.search(t)) for _n, rx in VERDICT_RX) + (
        frozenset(n for n, rx in TABLE_RX.items() if rx.search(t)),)


# ---------------------------------------------------------------- the reaching set
OPEN_PARAM, OPEN_UNBOUND, OPEN_ATTR, OPEN_CALL, OPEN_OTHER = "parameter", "unbound name", "attribute", "call", "other"
STR_METHODS = {"join", "format", "strip", "lstrip", "rstrip", "upper", "lower", "replace", "removeprefix",
               "removesuffix", "title", "capitalize", "ljust", "rjust", "center", "zfill"}


def fnode(q):
    return src.qdefs.get(q) if hasattr(src, "qdefs") and q in src.qdefs else src.defs.get(q)


def own(fn):
    todo = list(ast.iter_child_nodes(fn))
    while todo:
        n = todo.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield n
        todo.extend(ast.iter_child_nodes(n))


def params(fn):
    a = fn.args
    return {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs} | \
        ({a.vararg.arg} if a.vararg else set()) | ({a.kwarg.arg} if a.kwarg else set())


def bindings_in(nodes, name):
    """The value expressions bound to `name` among nodes (None: a binding with no readable value)."""
    out = []
    for n in nodes:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                out += _target_vals(t, n.value, name)
            if MUTATION:                          # a subscript store into `name` (the elif below never sees it)
                out += _mutation_vals(n, name, extra_only=True)
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == name:
            out.append(n.value)
        elif isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name) and n.target.id == name:
            out.append(n.value)
        elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
            out += _target_vals(n.target, ("ITER", n.iter), name)
        elif isinstance(n, ast.NamedExpr) and n.target.id == name:
            out.append(n.value)
        elif isinstance(n, ast.withitem) and n.optional_vars is not None:
            if any(isinstance(s, ast.Name) and s.id == name for s in ast.walk(n.optional_vars)):
                out.append(None)
        elif isinstance(n, ast.ExceptHandler) and n.name == name:
            out.append(None)
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in (
                "append", "extend", "insert") and isinstance(n.func.value, ast.Name) and n.func.value.id == name:
            out += list(n.args)
        elif MUTATION:
            out += _mutation_vals(n, name, extra_only=True)
    return out


def _mutation_vals(n, name, extra_only=False):
    """the stored values of one node that changes the container `name` in place."""
    if isinstance(n, ast.Assign):
        return [n.value for tg in n.targets for s in ast.walk(tg) if isinstance(s, ast.Subscript)
                and _base_name(s.value) == name and isinstance(s.ctx, ast.Store)]
    if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Subscript) and _base_name(n.target.value) == name:
        return [n.value]
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and _base_name(n.func.value) == name \
            and (isinstance(n.func.value, ast.Name) or n.func.attr in ("update", "setdefault", "add")):
        if n.func.attr in (("update", "setdefault", "add", "appendleft", "extendleft") if extra_only
                           else _MUT_METHODS):
            return list(n.args) + [k.value for k in n.keywords]
    if not extra_only and isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name) and n.target.id == name:
        return [n.value]
    return []


_GLOBAL_MUT, _PMOD, _ALLN = {}, {}, {}


def global_mutations(mod, name):
    """stores into the module-level container `name` of `mod` made inside any function of `mod` that does
    not bind `name` locally, or through `alias.name` in any read module."""
    k = (mod, name)
    if k not in _GLOBAL_MUT:
        vals = []
        for fn in ast.walk(trees[mod]):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and name not in params(fn):
                nodes = own_list(fn)
                if any(isinstance(g, ast.Global) and name in g.names for g in nodes):
                    continue                     # already a module binding
                if any(isinstance(s, ast.Name) and s.id == name and isinstance(s.ctx, ast.Store) for s in nodes):
                    continue                     # a local of the same name
                for n in nodes:
                    vals += [(fn, v) for v in _mutation_vals(n, name)]
        for m2, tr in trees.items():
            al = {a for a, tgt in ALIASES[m2].items() if tgt == mod}
            if not al:
                continue
            for n in ast.walk(tr):
                tgt = None
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in _MUT_METHODS:
                    tgt = n.func.value
                    got = list(n.args) + [kw.value for kw in n.keywords]
                elif isinstance(n, ast.Assign):
                    subs = [s for tg in n.targets for s in ast.walk(tg) if isinstance(s, ast.Subscript)
                            and isinstance(s.ctx, ast.Store)]
                    tgt = subs[0].value if subs else None
                    got = [n.value]
                if isinstance(tgt, ast.Attribute) and tgt.attr == name and isinstance(tgt.value, ast.Name) \
                        and tgt.value.id in al:
                    vals += [("MOD", m2, v) for v in got]
        _GLOBAL_MUT[k] = vals
    return _GLOBAL_MUT[k]


def passed_unread(scope_nodes, mod, name):
    """the calls in scope_nodes that take the container `name` whole and are not read: a callee the
    resolver cannot read and that is not a known non-changing built-in, or a read api function whose body
    changes that parameter in place."""
    out = []
    for c in scope_nodes:
        if not isinstance(c, ast.Call):
            continue
        idx = [i for i, a in enumerate(c.args) if isinstance(a, ast.Name) and a.id == name] + \
              [kw.arg for kw in c.keywords if isinstance(kw.value, ast.Name) and kw.value.id == name]
        if not idx:
            continue
        f = c.func
        if isinstance(f, ast.Name) and f.id in _PURE or isinstance(f, ast.Attribute) and f.attr in (
                "join", "format", "execute", "fetch", "fetchrow", "fetchval", "dumps", "copy", "count", "index",
                "startswith", "endswith", "get"):
            continue
        res = resolve_call(mod, f)
        if res is None:
            out.append("%s passed to %s at %d" % (name, ast.unparse(f)[:40], c.lineno))
            continue
        for m2, d in res:
            pos = [x.arg for x in d.args.posonlyargs + d.args.args]
            for i in idx:
                pn = pos[i] if isinstance(i, int) and i < len(pos) else i
                if isinstance(pn, str) and any(_mutation_vals(n, pn) for n in own_list(d)):
                    out.append("%s passed to %s.%s, which changes %s, at %d" % (name, m2, d.name, pn, c.lineno))
    return out


def _items_iter(v):
    """the receiver of `for k, v in X.items()` (DICT_PARTS), else None."""
    if DICT_PARTS and isinstance(v, tuple) and v[0] == "ITER" and isinstance(v[1], ast.Call) \
            and isinstance(v[1].func, ast.Attribute) and v[1].func.attr == "items" and not v[1].args:
        return v[1].func.value
    return None


def _target_vals(t, v, name):
    if isinstance(t, ast.Name):
        return [v] if t.id == name else []
    if isinstance(t, (ast.Tuple, ast.List)) and isinstance(v, ast.Call) and t.elts \
            and all(isinstance(e, ast.Name) for e in t.elts):
        # RULING-CENSUS-9 R1: the i-th name of a plain tuple target over a call; _reach decides whether the
        # call's returns are n-tuple displays (then the i-th elements alone) or not (then the whole call)
        return [("POS", v, i, len(t.elts)) for i, e in enumerate(t.elts) if e.id == name]
    if isinstance(t, (ast.Tuple, ast.List)):
        got = []
        recv = _items_iter(v)
        for i, e in enumerate(t.elts):
            if any(isinstance(s, ast.Name) and s.id == name for s in ast.walk(e)):
                if recv is not None and len(t.elts) == 2:
                    got += _target_vals(e, ("PART", "keys" if i == 0 else "values", recv), name)
                elif isinstance(v, (ast.Tuple, ast.List)) and len(v.elts) == len(t.elts):
                    got += _target_vals(e, v.elts[i], name)
                else:
                    got.append(v)           # the whole value: its constants reach every position
        return got
    if isinstance(t, ast.Starred):
        return _target_vals(t.value, v, name)
    return []


_MOD_IDX = {}
_FN_OWN = {}
_FN_B = {}


def own_list(fn):
    k = id(fn)
    if k not in _FN_OWN:
        _FN_OWN[k] = list(own(fn))
    return _FN_OWN[k]


def fn_bindings(fn, name):
    k = (id(fn), name)
    if k not in _FN_B:
        _FN_B[k] = bindings_in(own_list(fn), name)
    return _FN_B[k]


def _mod_index(mod):
    if mod not in _MOD_IDX:
        nodes, globs, imps = [], {}, {}
        for st in trees[mod].body:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(st, ast.ImportFrom) and st.module and st.level == 0:
                for al in st.names:
                    imps[al.asname or al.name] = (st.module.split(".")[-1], al.name)
            if not isinstance(st, (ast.Import, ast.ImportFrom)):
                nodes += [st] + list(own(st))
        for fn in ast.walk(trees[mod]):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for g in own_list(fn):
                    if isinstance(g, ast.Global):
                        for nm in g.names:
                            globs.setdefault(nm, []).append(fn)
        _MOD_IDX[mod] = (nodes, globs, imps, {})
    return _MOD_IDX[mod]


def module_bindings(mod, name):
    nodes, globs, imps, memo = _mod_index(mod)
    if name not in memo:
        vals = bindings_in(nodes, name)
        for fn in globs.get(name, []):        # a `global name` rebinding inside a function counts
            vals += fn_bindings(fn, name)
        memo[name] = (vals, imps.get(name))
    return memo[name]


class Reach:
    def __init__(self):
        self.consts, self.open, self.number = set(), [], True
        self.proved, self.revisit = False, False      # a number shown by _is_number / range; a seen node
        self.idents = True

    def add_const(self, c):
        self.consts.add(c)
        self.number = False


def reach(expr, fn, mod, R=None, seen=None):
    R = R if R is not None else Reach()
    seen = seen if seen is not None else set()
    _reach(expr, fn, mod, R, seen)
    return R


def _is_number(x, fn, mod, seen=()):
    if isinstance(x, ast.Constant) and isinstance(x.value, (int, float)) and not isinstance(x.value, bool):
        return True
    if isinstance(x, ast.Call) and isinstance(x.func, ast.Name):
        if x.func.id in ("int", "len", "round"):
            return True
        if x.func.id in ("max", "min") and any(isinstance(a, ast.Constant) and isinstance(a.value, (int, float))
                                               for a in x.args):
            return True
    if isinstance(x, ast.BinOp) and not isinstance(x.op, ast.Mod) or isinstance(x, ast.BinOp) and isinstance(
            x.op, ast.Mod) and not (isinstance(x.left, ast.Constant) and isinstance(x.left.value, str)):
        return _is_number(x.left, fn, mod, seen) and _is_number(x.right, fn, mod, seen)
    if isinstance(x, ast.UnaryOp):
        return _is_number(x.operand, fn, mod, seen)
    if isinstance(x, ast.Name) and x.id not in seen and fn is not None:
        if x.id in params(fn):
            return False
        vals = fn_bindings(fn, x.id)
        if not vals:
            vals, _imp = module_bindings(mod, x.id)
        return bool(vals) and all(v is not None and not isinstance(v, tuple)
                                  and _is_number(v, fn, mod, seen + (x.id,)) for v in vals)
    return False


_FNC = {}
FUNCS, FROMS, ALIASES = {}, {}, {}
for _m, _t in trees.items():
    FUNCS[_m], FROMS[_m], ALIASES[_m] = defaultdict(list), {}, {}
    for _n in ast.walk(_t):
        if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            FUNCS[_m][_n.name].append(_n)
    for _st in _t.body:
        if isinstance(_st, ast.ImportFrom):
            if _st.module and _st.module.split(".")[-1] in trees:
                for _a in _st.names:
                    FROMS[_m][_a.asname or _a.name] = (_st.module.split(".")[-1], _a.name)
            elif not _st.module or _st.level:
                for _a in _st.names:
                    if _a.name in trees:
                        ALIASES[_m][_a.asname or _a.name] = _a.name
        elif isinstance(_st, ast.Import):
            for _a in _st.names:
                if _a.name.split(".")[-1] in trees:
                    ALIASES[_m][_a.asname or _a.name.split(".")[-1]] = _a.name.split(".")[-1]


def resolve_call(mod, f):
    """[(module, def node)] a call's callee can be among the api modules, or None."""
    if isinstance(f, ast.Name):
        if FUNCS[mod].get(f.id):
            return [(mod, n) for n in FUNCS[mod][f.id]]
        if f.id in FROMS[mod]:
            m2, n2 = FROMS[mod][f.id]
            if FUNCS[m2].get(n2):
                return [(m2, n) for n in FUNCS[m2][n2]]
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in ALIASES[mod]:
        m2 = ALIASES[mod][f.value.id]
        if FUNCS[m2].get(f.attr):
            return [(m2, n) for n in FUNCS[m2][f.attr]]
    return None


def docstrings(fn):
    return {id(st.value) for st in ast.walk(fn) if isinstance(st, ast.Expr)
            and isinstance(st.value, ast.Constant) and isinstance(st.value.value, str)}


def fn_closure_consts(mod, fn, seen=None):
    """every string constant of a def's body (docstrings and other bare string statements, which no
    value carries, left out), of every api def it calls, and of the module names it names."""
    top = seen is None
    if top and id(fn) in _FNC:
        return _FNC[id(fn)]
    seen = set() if seen is None else seen
    cs, op = set(), []
    if id(fn) in seen:
        return cs, op
    seen.add(id(fn))
    skip = docstrings(fn)
    for n in ast.walk(fn):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip:
            cs.add(n.value)
        elif isinstance(n, ast.Call):
            for m2, d in resolve_call(mod, n.func) or []:
                c2, o2 = fn_closure_consts(m2, d, seen)
                cs |= c2
                op += o2
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            vals, imp = module_bindings(mod, n.id)
            if not vals and imp and imp[0] in trees:
                vals, _ = module_bindings(imp[0], imp[1])
            for v in vals:
                if v is not None and not isinstance(v, tuple) and ("mn", id(v)) not in seen:
                    seen.add(("mn", id(v)))
                    cs |= {c.value for c in ast.walk(v) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    if top:
        _FNC[id(fn)] = (cs, op)
    return cs, op


def _fn_consts(mod, q, R, seen):
    """every string constant of a read function's body, of what it calls and of the module names it names
    (computed once per function, over its whole call closure)."""
    if q not in _FNC:
        R2, seen2 = Reach(), set()
        _fn_consts_raw(mod, q, R2, seen2)
        _FNC[q] = (set(R2.consts), list(R2.open))
    cs, op = _FNC[q]
    for c in cs:
        R.add_const(c)
    R.open += op


def _fn_consts_raw(mod, q, R, seen):
    if ("fn", mod, q) in seen:
        return
    seen.add(("fn", mod, q))
    fn = fnode(q)
    if fn is None:
        R.open.append((OPEN_CALL, q))
        return
    for n in ast.walk(fn):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            R.add_const(n.value)
        elif isinstance(n, ast.Call):
            target = src.resolve(q, n.func.id) if isinstance(n.func, ast.Name) else None
            if target is not None:
                _fn_consts_raw(mc.mod_of(target), target, R, seen)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            vals, _imp = module_bindings(mc.mod_of(q), n.id)
            for v in vals:
                if v is not None and not isinstance(v, tuple) and ("mn", mod, n.id) not in seen:
                    seen.add(("mn", mod, n.id))
                    for c in ast.walk(v):
                        if isinstance(c, ast.Constant) and isinstance(c.value, str):
                            R.add_const(c.value)


def _reach_part(x, part, fn, mod, R, seen):
    """DICT_PARTS: the keys or the values of a dictionary expression. A Dict literal gives that part;
    a name gives that part of each of its bindings; a subscript of a dictionary of dictionaries gives
    that part of each inner value; anything else is reached whole."""
    if not (DICT_PARTS and _STRICT[0] == 0):
        _reach(x, fn, mod, R, seen)
        return
    if isinstance(x, ast.Name):
        d = _dict_display(x, fn, mod)
        if d is None:
            _reach(x, fn, mod, R, seen)
            return
        x = d
    if isinstance(x, ast.Dict):
        for k, v in zip(x.keys, x.values):
            e = k if part == "keys" else v
            if e is None:                       # {**other}
                _reach_part(v, part, fn, mod, R, seen)
            else:
                _reach(e, fn, mod, R, seen)
        return
    if isinstance(x, ast.Name):
        key = ("part", part, id(fn), x.id)
        if key in seen:
            R.revisit = True
            return
        seen.add(key)
        if fn is not None and x.id in params(fn):
            R.open.append((OPEN_PARAM, x.id))
            return
        vals = fn_bindings(fn, x.id) if fn is not None else []
        scope_fn = fn
        if not vals:
            vals, imp = module_bindings(mod, x.id)
            scope_fn = None
            if not vals and imp and imp[0] in trees:
                vals, _ = module_bindings(imp[0], imp[1])
                mod = imp[0]
        if not vals:
            R.open.append((OPEN_UNBOUND, x.id))
            return
        for v in vals:
            if v is None or isinstance(v, tuple):
                _reach(v, scope_fn, mod, R, seen)
            else:
                _reach_part(v, part, scope_fn, mod, R, seen)
        return
    if isinstance(x, ast.Subscript):
        inner = Reach()
        _reach_part(x.value, "values", fn, mod, inner, seen)   # the inner dictionaries, whole
        # an inner dictionary's part: read it from the literal when the outer value is a Dict of Dicts
        lit = _dict_display(x.value, fn, mod)
        if lit is not None and all(isinstance(v, ast.Dict) for v in lit.values):
            for v in lit.values:
                _reach_part(v, part, fn, mod, R, seen)
            return
        for c in inner.consts:
            R.add_const(c)
        R.open += inner.open
        return
    _reach(x, fn, mod, R, seen)


_CHANGED = None


def _base_name(e):
    """the name at the base of a subscript / attribute chain, or None."""
    while isinstance(e, (ast.Subscript, ast.Attribute)):
        e = e.value
    return e.id if isinstance(e, ast.Name) else None


def _dict_changed_names():
    """names some read module changes in place (subscript store or delete, update, setdefault, pop,
    clear, popitem, |=) or passes whole to a call; by name, in every read module."""
    global _CHANGED
    if _CHANGED is None:
        ch = set()
        for tr in trees.values():
            for n in ast.walk(tr):
                if isinstance(n, ast.Subscript) and isinstance(n.ctx, (ast.Store, ast.Del)) \
                        and _base_name(n.value):
                    ch.add(_base_name(n.value))
                elif isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name):
                    ch.add(n.target.id)
                elif isinstance(n, ast.Call):
                    f = n.func
                    if isinstance(f, ast.Attribute) and _base_name(f.value) and f.attr in (
                            "update", "setdefault", "pop", "clear", "popitem"):
                        ch.add(_base_name(f.value))
                    for a in list(n.args) + [k.value for k in n.keywords]:
                        if isinstance(a, ast.Name):
                            ch.add(a.id)
                        elif isinstance(a, ast.Starred) and isinstance(a.value, ast.Name):
                            ch.add(a.value.id)
        _CHANGED = ch
    return _CHANGED


def _dict_display(x, fn, mod, hop=0):
    """RULING-CENSUS-4 2(a)(b) with RULING-CENSUS-5 sec 2: the display itself, or a name bound exactly once
    to a display that no read module changes or passes whole, or a name bound exactly once to such a name
    (or to it as an attribute of a read module): a chain of at most two names, (b) checked for each."""
    if isinstance(x, ast.Dict):
        return x
    vals, vmod, vfn = [], mod, fn
    if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and x.value.id in ALIASES.get(mod, {}):
        vmod, vfn = ALIASES[mod][x.value.id], None
        vals, _ = module_bindings(vmod, x.attr)
        nm = x.attr
    elif isinstance(x, ast.Name):
        nm = x.id
        vals = fn_bindings(fn, x.id) if fn is not None else []
        if not vals and not (fn is not None and x.id in params(fn)):
            vfn = None
            vals, imp = module_bindings(mod, x.id)
            if not vals and imp and imp[0] in trees:
                vmod = imp[0]
                vals, _ = module_bindings(imp[0], imp[1])
    else:
        return None
    if len(vals) != 1 or nm in _dict_changed_names():
        return None
    v = vals[0]
    if isinstance(v, ast.Dict):
        return v
    if hop == 0 and isinstance(v, (ast.Name, ast.Attribute)):
        return _dict_display(v, vfn, vmod, 1)
    return None


def _const_text(e, fn, mod, depth=0):
    """one exact text, or None: a str constant, + of texts, an f-string of constants, a name bound once."""
    if depth > 6 or e is None or isinstance(e, tuple):
        return None
    if isinstance(e, ast.Constant) and isinstance(e.value, str):
        return e.value
    if isinstance(e, ast.BinOp) and isinstance(e.op, ast.Add):
        a, b = _const_text(e.left, fn, mod, depth + 1), _const_text(e.right, fn, mod, depth + 1)
        return None if a is None or b is None else a + b
    if isinstance(e, ast.JoinedStr) and all(isinstance(v, ast.Constant) for v in e.values):
        return "".join(str(v.value) for v in e.values)
    if isinstance(e, ast.Name):
        vals, scope = (fn_bindings(fn, e.id) if fn is not None else []), fn
        if not vals and not (fn is not None and e.id in params(fn)):
            vals, _ = module_bindings(mod, e.id)
            scope = None
        if len(vals) == 1:
            return _const_text(vals[0], scope, mod, depth + 1)
    return None


def expansion_values(hn, fn, mod):
    """RULING-CENSUS-4 section 3: the hole IS a whole value of a display (the value target of a loop over
    its items() or values(), a subscript of it, or a name bound once to either); the exact texts, or None."""
    recv, extra = None, []
    if isinstance(hn, ast.Subscript):
        recv = hn.value
    elif isinstance(hn, ast.Name) and fn is not None and hn.id not in params(fn) and len(fn_bindings(fn, hn.id)) == 1:
        for n in own_list(fn):
            if isinstance(n, (ast.For, ast.AsyncFor)):
                t, it = n.target, n.iter
                if not (isinstance(it, ast.Call) and isinstance(it.func, ast.Attribute) and not it.args):
                    continue
                if it.func.attr == "items" and isinstance(t, ast.Tuple) and len(t.elts) == 2 \
                        and isinstance(t.elts[1], ast.Name) and t.elts[1].id == hn.id:
                    recv = it.func.value
                elif it.func.attr == "values" and isinstance(t, ast.Name) and t.id == hn.id:
                    recv = it.func.value
            elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
                    and n.targets[0].id == hn.id:
                v = n.value
                if isinstance(v, ast.Subscript):
                    recv = v.value
                elif isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and v.func.attr == "get" \
                        and 1 <= len(v.args) <= 2 and not v.keywords:
                    recv, extra = v.func.value, list(v.args[1:])
    if recv is None:
        return None
    disp = _dict_display(recv, fn, mod)
    if disp is None or any(k is None for k in disp.keys):
        return None
    out = set()
    for v in list(disp.values) + extra:
        if VALUE or PARAM:
            s = exact_texts(v, fn, mod)
        else:
            c1 = _const_text(v, fn, mod)
            s = None if c1 is None else [c1]
        if s is None:
            return None
        out |= set(s)
    return sorted(out) if out else None


_PSTACK = []
_CALLERS = None
_ALIAS_STORES = None
_DEFS_BY_MOD = {}


def _alias_stores():
    """(module, NAME) stored through `alias.NAME` (assignment or augmented assignment) in any read module."""
    global _ALIAS_STORES
    if _ALIAS_STORES is None:
        s = set()
        for m2, tr in trees.items():
            for n in ast.walk(tr):
                tg = n.targets if isinstance(n, ast.Assign) else [n.target] if isinstance(n, ast.AugAssign) else []
                for g in tg:
                    for a in ast.walk(g):
                        if isinstance(a, ast.Attribute) and isinstance(a.ctx, ast.Store) \
                                and isinstance(a.value, ast.Name) and a.value.id in ALIASES[m2]:
                            s.add((ALIASES[m2][a.value.id], a.attr))
        _ALIAS_STORES = s
    return _ALIAS_STORES


def _value_name_ok(m, nm):
    """RULING-CENSUS-5 4(b): bound exactly once at module level, no `global` names it, no store through
    alias.NAME, no augmented assignment, no store of the MUTATION kind."""
    nodes, globs, _imps, _memo = _mod_index(m)
    vals = bindings_in(nodes, nm)
    if len(vals) != 1 or not isinstance(vals[0], ast.expr) or nm in globs or (m, nm) in _alias_stores():
        return None
    if any(isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name) and n.target.id == nm for n in nodes):
        return None
    if any(_mutation_vals(n, nm) for n in nodes) or global_mutations(m, nm):
        return None
    return vals[0]


_PASS_CALLS = {"str", "sorted", "list", "tuple", "set", "frozenset", "len", "range", "enumerate", "zip", "dict",
               "int", "float", "bool", "isinstance", "any", "all", "min", "max", "sum", "reversed", "repr",
               "RuntimeError", "ValueError", "AssertionError", "KeyError", "TypeError"}
_PASS_ATTRS = set(STR_METHODS) | {"items", "values", "keys", "get", "copy", "append", "extend", "insert", "add",
                                  "update", "setdefault", "count", "index", "pop", "sort"}
# RULING-CENSUS-6 section 2: str methods, compiled-pattern methods and the re module's functions pass in the
# closure walk: a module-level receiver by its TYPE (from the child), a local receiver by the method's name
_STR_PAT_METHODS = {a for a in dir(str) if not a.startswith("_")} | {
    a for a in dir(type(re.compile(""))) if not a.startswith("_")}
_RE_FUNCS = {"compile", "escape", "match", "fullmatch", "search", "findall", "sub", "subn", "split",
             "IGNORECASE", "I", "MULTILINE", "M", "DOTALL", "S", "VERBOSE", "X", "ASCII", "A"}
_VC = {}
VALUE_WHY = {}
_RE_NAMES = {}


def _re_names(m):
    """the module-level names under which module m imports the re module (import re / import re as X)."""
    if m not in _RE_NAMES:
        _RE_NAMES[m] = {a.asname or a.name for st in trees[m].body if isinstance(st, ast.Import)
                        for a in st.names if a.name == "re"}
    return _RE_NAMES[m]
_INIT_OF = None


def value_closed(expr, fn, mod):
    """RULING-CENSUS-5 4(c): (closed, reason). The strict reach must be closed, and the whole closure of the
    expression -- module names it reads, read functions it calls, transitively -- may read no attribute of
    an object other than through a string, dictionary or list method, and may call nothing outside the read
    modules but the passing built-ins."""
    k = (mod, id(expr))
    if k in _VC:
        return _VC[k]
    R = reach(expr, fn, mod)
    if R.open:
        _VC[k] = (False, "the reach is open: %s" % (R.open[0],))
        return _VC[k]
    todo, seen, why = [(expr, mod)], set(), None
    while todo and why is None:
        node, m = todo.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        funcs = {id(c.func) for c in ast.walk(node) if isinstance(c, ast.Call)}
        own_n = _own_names(node)
        for n in ast.walk(node):
            if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load):
                if isinstance(n.value, ast.Name) and (n.value.id in ALIASES[m] or n.value.id in trees):
                    m2 = ALIASES[m].get(n.value.id, n.value.id)
                    iv, _ = module_bindings(m2, n.attr)
                    if iv and _value_name_ok(m2, n.attr) is None:
                        why = "the module name %s.%s is bound more than once or changed after import" % (m2, n.attr)
                        break
                    todo += [(v, m2) for v in iv if isinstance(v, ast.expr)]
                    todo += [(d, m2) for d in FUNCS[m2].get(n.attr, [])]
                    continue
                if n.attr in _PASS_ATTRS and id(n) in funcs:
                    continue                                      # the standing methods
                if (id(n) in funcs or isinstance(n.value, ast.Name) and n.value.id in _re_names(m)) \
                        and _method_passes(n, m, node):
                    continue
                why = "an attribute read %s in %s" % (ast.unparse(n)[:50], m)
                break
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                res = resolve_call(m, n.func)
                if res:
                    todo += [(d, m2) for m2, d in res]
                elif n.func.id not in _PASS_CALLS:
                    why = "a call of %s in %s" % (n.func.id, m)
                    break
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                iv, imp = module_bindings(m, n.id)
                if iv and n.id not in own_n and _value_name_ok(m, n.id) is None:
                    why = "the module name %s.%s is bound more than once or changed after import" % (m, n.id)
                    break
                todo += [(v, m) for v in iv if isinstance(v, ast.expr)]
                todo += [(d, m) for d in FUNCS[m].get(n.id, [])]   # (c): a named read function is walked
                if not iv and imp and imp[0] in trees:
                    iv2, _ = module_bindings(imp[0], imp[1])
                    if iv2 and n.id not in own_n and _value_name_ok(imp[0], imp[1]) is None:
                        why = "the module name %s.%s is bound more than once or changed after import" % imp
                        break
                    todo += [(v, imp[0]) for v in iv2 if isinstance(v, ast.expr)]
                    todo += [(d, imp[0]) for d in FUNCS[imp[0]].get(imp[1], [])]
    _VC[k] = (why is None, why or "")
    return _VC[k]


def _own_names(node):
    """the names node binds itself: a def's parameters and every name stored in its body, and the targets of
    every comprehension inside node (each its own scope); a module name of the same spelling is shadowed."""
    out = set()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        out |= params(node)
        out |= {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del))}
    for c in ast.walk(node):
        if isinstance(c, ast.comprehension):
            out |= {n.id for n in ast.walk(c.target) if isinstance(n, ast.Name)}
    return out


_ML = {}


def _module_level(name, m, scope):
    """the name is a module-level name of m where scope uses it: m binds it (or imports re as it) and scope
    binds it nowhere (no parameter, no store)."""
    k = (id(scope), name, m)
    if k not in _ML:
        ok = name in _re_names(m) or bool(module_bindings(m, name)[0])
        if ok:
            for s in ast.walk(scope):
                if isinstance(s, ast.arg) and s.arg == name or isinstance(s, ast.Name) and s.id == name \
                        and isinstance(s.ctx, (ast.Store, ast.Del)):
                    ok = False
                    break
        _ML[k] = ok
    return _ML[k]


def _method_passes(n, m, scope):
    """RULING-CENSUS-6 2(a)(b): a str / compiled-pattern method, or a function of the re module."""
    recv, attr = n.value, n.attr
    if isinstance(recv, ast.Name) and _module_level(recv.id, m, scope):
        if attr not in _STR_PAT_METHODS and attr not in _RE_FUNCS:
            return False
        key = m + "|" + recv.id
        if VALUE_COLLECT:
            VALUE_REQ.setdefault(key, [m, recv.id, True])
            return True
        v = VALUES.get(key) or {}
        if v.get("type") == "module":
            return v.get("module") == "re" and attr in _RE_FUNCS
        return v.get("type") in ("str", "Pattern") and attr in _STR_PAT_METHODS
    return attr in _STR_PAT_METHODS                              # (b): a local receiver, by name


def _init_of():
    global _INIT_OF
    if _INIT_OF is None:
        _INIT_OF = {}
        for m, tr in trees.items():
            for st in tr.body:
                if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
                    _INIT_OF[id(st.value)] = (m, st.targets[0].id)
    return _INIT_OF


def _name_candidate(m, nm):
    init = _value_name_ok(m, nm)
    if init is None:
        return None
    ok, why = value_closed(init, None, m)
    VALUE_WHY[m + "|" + nm] = why
    return (m, nm, ok)


def value_candidate(e, fn, mod):
    """RULING-CENSUS-5 4(a)(b): (module, source to evaluate there, closed) or None."""
    if isinstance(e, ast.Name):
        if fn is not None and (e.id in params(fn) or fn_bindings(fn, e.id)):
            return None
        m, nm = mod, e.id
        _v, imp = module_bindings(m, nm)
        if not _v and imp and imp[0] in trees:
            m, nm = imp
        return _name_candidate(m, nm)
    if isinstance(e, ast.Attribute) and isinstance(e.value, ast.Name) and e.value.id in ALIASES.get(mod, {}):
        return _name_candidate(ALIASES[mod][e.value.id], e.attr)
    if isinstance(e, ast.Subscript):
        sl = e.slice
        if not (isinstance(sl, ast.Constant) or isinstance(sl, ast.Tuple)
                and all(isinstance(x, ast.Constant) for x in sl.elts)):
            return None
        base = value_candidate(e.value, fn, mod)
        if base is None:
            return None
        return (base[0], base[1] + "[" + ast.unparse(sl) + "]", base[2])
    if isinstance(e, ast.Call) and id(e) in _init_of():
        return _name_candidate(*_init_of()[id(e)])      # the call IS a module name's initializer
    if isinstance(e, ast.Call):
        if not all(isinstance(a, ast.Constant) for a in e.args) \
                or not all(k.arg is not None and isinstance(k.value, ast.Constant) for k in e.keywords):
            return None
        res = resolve_call(mod, e.func)
        if not res or len(res) != 1:
            return None
        m2, d = res[0]
        if d not in trees[m2].body:
            return None                                   # a module-level function only
        call = d.name + "(" + ", ".join([ast.unparse(a) for a in e.args]
                                        + ["%s=%s" % (k.arg, ast.unparse(k.value)) for k in e.keywords]) + ")"
        ok, why = value_closed(e, fn, mod)
        VALUE_WHY[m2 + "|" + call] = why
        return (m2, call, ok)
    return None


def _value_of(e, fn, mod, want_seq=False):
    """the child's value of a VALUE candidate: [text] (want_seq False) or [element texts]; None if not read."""
    if not VALUE:
        return None
    c = value_candidate(e, fn, mod)
    if c is None:
        return None
    key = c[0] + "|" + c[1]
    if isinstance(e, ast.Call) and not c[2]:
        return None                                       # a call that is not closed is never evaluated
    if VALUE_COLLECT:
        VALUE_REQ[key] = [c[0], c[1], c[2]]
        return None
    v = VALUES.get(key)
    if not isinstance(v, dict) or v.get("value") is None:
        return None
    val = v["value"]
    if want_seq and isinstance(val, list) and all(isinstance(s, str) for s in val):
        out = val
    elif not want_seq and isinstance(val, str):
        out = [val]
    else:
        return None
    if not c[2]:
        _JUDGED_USE.append(key)
    return out


def _cap(xs):
    return xs if xs is not None and len(xs) <= 64 else None


def exact_seq(e, fn, mod, depth=0):
    """the element texts of a sequence, exactly, or None."""
    if depth > 6:
        return None
    if isinstance(e, (ast.Tuple, ast.List)):
        out = []
        for x in e.elts:
            s = exact_texts(x, fn, mod, depth + 1)
            if s is None or len(s) != 1:
                return None
            out += s
        return out
    if isinstance(e, ast.BinOp) and isinstance(e.op, ast.Add):
        a, b = exact_seq(e.left, fn, mod, depth + 1), exact_seq(e.right, fn, mod, depth + 1)
        return None if a is None or b is None else a + b
    if isinstance(e, ast.Name) and fn is not None and e.id not in params(fn):
        vals = fn_bindings(fn, e.id)
        if len(vals) == 1 and isinstance(vals[0], ast.expr):
            return exact_seq(vals[0], fn, mod, depth + 1)
    return _value_of(e, fn, mod, want_seq=True)


def exact_texts(e, fn, mod, depth=0):
    """every text the expression can take, exactly (at most 64), or None."""
    if depth > 8 or e is None or isinstance(e, tuple):
        return None
    if isinstance(e, ast.Constant) and isinstance(e.value, str):
        return [e.value]
    if isinstance(e, ast.BinOp) and isinstance(e.op, ast.Add):
        a, b = exact_texts(e.left, fn, mod, depth + 1), exact_texts(e.right, fn, mod, depth + 1)
        if a is None or b is None or len(a) * len(b) > 64:
            return None
        return sorted({x + y for x in a for y in b})
    if isinstance(e, ast.JoinedStr):
        acc = [""]
        for v in e.values:
            if isinstance(v, ast.Constant):
                part = [str(v.value)]
            elif isinstance(v, ast.FormattedValue) and v.format_spec is None and v.conversion in (-1, 115):
                part = exact_texts(v.value, fn, mod, depth + 1)
            else:
                return None
            if part is None or len(acc) * len(part) > 64:
                return None
            acc = [x + y for x in acc for y in part]
        return sorted(set(acc))
    if isinstance(e, ast.IfExp):
        a, b = exact_texts(e.body, fn, mod, depth + 1), exact_texts(e.orelse, fn, mod, depth + 1)
        return None if a is None or b is None else _cap(sorted(set(a) | set(b)))
    if isinstance(e, ast.Call) and isinstance(e.func, ast.Attribute) and e.func.attr == "join" \
            and len(e.args) == 1 and not e.keywords:
        sep = exact_texts(e.func.value, fn, mod, depth + 1)
        seq = exact_seq(e.args[0], fn, mod, depth + 1)
        if sep is None or len(sep) != 1 or seq is None:
            return None
        return [sep[0].join(seq)]
    if isinstance(e, ast.Name):
        if fn is not None and e.id in params(fn):
            if not PARAM or len(_PSTACK) >= 3 or (id(fn), e.id) in _PSTACK:
                return None
            args, fails_ = param_calls(fn, mod, e.id)
            if fails_ or not args:
                return None
            _PSTACK.append((id(fn), e.id))
            try:
                out = set()
                for cmod, cfn, a in args:
                    s = exact_texts(a, cfn, cmod, depth + 1)
                    if s is None:
                        return None
                    out |= set(s)
            finally:
                _PSTACK.pop()
            return _cap(sorted(out))
        if fn is not None:
            nc = bindings_in([n for n in own_list(fn) if not isinstance(n, ast.comprehension)], e.id)
            if nc:
                return exact_texts(nc[0], fn, mod, depth + 1) if len(nc) == 1 else None
        vals, imp = module_bindings(mod, e.id)
        m = mod
        if not vals and imp and imp[0] in trees:
            m = imp[0]
            vals, _ = module_bindings(imp[0], imp[1])
        if len(vals) == 1 and isinstance(vals[0], ast.expr):
            s = exact_texts(vals[0], None, m, depth + 1)
            if s is not None:
                return s
        return _value_of(e, fn, mod)
    if isinstance(e, (ast.Subscript, ast.Call, ast.Attribute)):
        return _value_of(e, fn, mod)
    return None


def as_trees_def(mod, d):
    """(def, why): the def of trees[mod] that the reader's def d stands for. d itself when trees holds it (one
    parse, RULING-CENSUS-8 (a)); else the one def of the same name and first line. Two such defs or none is a
    closed failure (why names it, and the def handed back is d): the caller and method indexes are keyed by
    the identity of trees' defs, and a def they do not hold has no caller there."""
    if d is None or mod not in trees:
        return d, None
    if mod not in _DEFS_BY_MOD:
        _DEFS_BY_MOD[mod] = [x for x in ast.walk(trees[mod]) if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if any(x is d for x in _DEFS_BY_MOD[mod]):
        return d, None
    same = [x for x in _DEFS_BY_MOD[mod] if x.name == d.name and x.lineno == d.lineno]
    if len(same) == 1:
        return same[0], None
    return d, "%s.%s:%d maps to %d defs of %s" % (mod, d.name, d.lineno, len(same), mod)


def enclosing_def(mod, node):
    if mod not in _DEFS_BY_MOD:
        _DEFS_BY_MOD[mod] = [d for d in ast.walk(trees[mod]) if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef))]
    best = None
    for d in _DEFS_BY_MOD[mod]:
        if d.lineno <= node.lineno <= d.end_lineno and (best is None or d.lineno > best.lineno):
            best = d
    return best


def _callers():
    """id(def) -> [(module, enclosing def or None, call)] for every call the index resolves; and
    id(def) -> [where] for every use of its name other than as a callee."""
    global _CALLERS
    if _CALLERS is None:
        calls, uses = defaultdict(list), defaultdict(list)
        for m, tr in trees.items():
            enclosing = {}
            for fd in ast.walk(tr):
                if isinstance(fd, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for n in own_list(fd):
                        enclosing.setdefault(id(n), fd)
            funcs = set()
            for n in ast.walk(tr):
                if isinstance(n, ast.Call):
                    funcs.add(id(n.func))
                    for m2, d in resolve_call(m, n.func) or []:
                        calls[id(d)].append((m, enclosing.get(id(n)), n))
            for n in ast.walk(tr):
                if isinstance(n, (ast.Name, ast.Attribute)) and id(n) not in funcs \
                        and isinstance(getattr(n, "ctx", None), ast.Load):
                    for m2, d in resolve_call(m, n) or []:
                        e = enclosing.get(id(n))
                        uses[id(d)].append("%s.%s:%d" % (m, e.name if e else "<module>", n.lineno))
        _CALLERS = (calls, uses)
    return _CALLERS


METHOD_CALLS = {}
_METHODS = None


def _is_method(fn):
    global _METHODS
    if _METHODS is None:
        _METHODS = {id(d) for tr in trees.values() for c in ast.walk(tr) if isinstance(c, ast.ClassDef)
                    for d in c.body if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return id(fn) in _METHODS


def param_calls(fn, mod, pname):
    """([(caller module, caller def, argument expression)], [closed failure naming the caller])."""
    calls, uses = _callers()
    a = fn.args
    pos = [x.arg for x in a.posonlyargs + a.args]
    out, fails_ = [], []
    if a.vararg and pname == a.vararg.arg or a.kwarg and pname == a.kwarg.arg:
        fails_.append("a star parameter %s of %s.%s" % (pname, mod, fn.name))
        return out, fails_
    if _is_method(fn):
        recv = Counter()
        for tr in trees.values():
            for c in ast.walk(tr):
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == fn.name \
                        and (c.args or c.keywords):
                    recv[ast.unparse(c.func.value)[:40]] += 1
        METHOD_CALLS[(mod, fn.name)] = recv
        fails_.append("the method %s.%s: %d attribute calls of that name with an argument, receivers %s" % (
            mod, fn.name, sum(recv.values()), sorted(recv.items(), key=lambda kv: -kv[1])[:12]))
        return out, fails_
    if any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in (
            "get", "post", "put", "patch", "delete", "websocket", "api_route") or isinstance(d, ast.Attribute)
           and d.attr in ("get", "post", "put", "patch", "delete", "websocket", "api_route")
           for d in fn.decorator_list):
        fails_.append("%s.%s is a route handler" % (mod, fn.name))
    for w in uses.get(id(fn), []):
        fails_.append("%s.%s used other than as a callee at %s" % (mod, fn.name, w))
    defaults = dict(zip(pos[len(pos) - len(a.defaults):], a.defaults)) if a.defaults else {}
    defaults.update({k.arg: d for k, d in zip(a.kwonlyargs, a.kw_defaults) if d is not None})
    if pname in defaults:
        out.append((mod, None, defaults[pname]))
    for cmod, cfn, c in calls.get(id(fn), []):
        where = "%s.%s:%d" % (cmod, cfn.name if cfn else "<module>", c.lineno)
        if any(k.arg is None for k in c.keywords):
            fails_.append("a double-star argument at %s" % where)
            continue
        kw = [k.value for k in c.keywords if k.arg == pname]
        stars = [i for i, x in enumerate(c.args) if isinstance(x, ast.Starred)]
        if stars and not kw:
            k0 = stars[0]
            if len(stars) > 1 or k0 != len(c.args) - 1:
                fails_.append("a star argument that is not the last positional at %s" % where)
            elif pname in pos and pos.index(pname) < k0:
                out.append((cmod, cfn, c.args[pos.index(pname)]))
            elif pname in pos:                    # R2: the star fills it with the starred expression's reach
                out.append((cmod, cfn, ("STAR", c.args[k0].value, _enclosing_comps(cmod, c))))
            continue
        if kw:
            out.append((cmod, cfn, kw[0]))
        elif pname in pos and pos.index(pname) < len(c.args):
            out.append((cmod, cfn, c.args[pos.index(pname)]))
    return out, fails_


def _reach(x, fn, mod, R, seen):
    if x is None:
        R.open.append((OPEN_OTHER, "a binding with no value"))
        return
    if isinstance(x, tuple) and x[0] == "ITER":       # a loop target: the iterable's elements
        it = x[1]
        if DICT_PARTS and _STRICT[0] == 0 and isinstance(it, ast.Call) and isinstance(it.func, ast.Attribute) \
                and not it.args and it.func.attr in ("values", "keys"):
            _reach_part(it.func.value, it.func.attr, fn, mod, R, seen)
        else:
            _reach(it, fn, mod, R, seen)
        return
    if isinstance(x, tuple) and x[0] == "PART":
        _reach_part(x[2], x[1], fn, mod, R, seen)
        return
    if isinstance(x, tuple) and x[0] == "STAR":       # R2: the whole reach of the starred expression
        e, comps = x[1], x[2]
        if isinstance(e, ast.Name):
            vals = bindings_in(comps, e.id)
            if vals:
                for v in vals:
                    _reach(v, fn, mod, R, seen)
                return
        _reach(e, fn, mod, R, seen)
        return
    if isinstance(x, tuple) and x[0] == "POS":        # R1: one position of a call's tuple returns
        _, call, i, n = x
        targets = _call_targets(call, fn, mod)
        rets = {id(d): _pos_returns(d, n) for _m2, d in targets or []}
        if targets and all(rets[id(d)] is not None for _m2, d in targets):
            for m2, d in targets:
                key = ("pos", id(d), id(call), i)
                if key in seen:
                    R.revisit = True
                    continue
                seen.add(key)
                _reach_bound(m2, d, [r.elts[i] for r in rets[id(d)]], R, seen, call, fn, mod)
        else:
            _reach(call, fn, mod, R, seen)
        return
    if _is_number(x, fn, mod):
        R.proved = True
        return
    if isinstance(x, ast.Constant):
        R.add_const(str(x.value))
        return
    if isinstance(x, (ast.JoinedStr, ast.Tuple, ast.List, ast.Set, ast.BoolOp, ast.Dict, ast.FormattedValue,
                      ast.IfExp, ast.Compare)):
        for c in ast.iter_child_nodes(x):
            if isinstance(x, ast.IfExp) and c is x.test or isinstance(x, ast.Compare):
                continue
            if isinstance(c, ast.expr):
                _reach(c, fn, mod, R, seen)
        if isinstance(x, ast.Compare):
            R.add_const("True")
        return
    if isinstance(x, ast.BinOp):
        _reach(x.left, fn, mod, R, seen)
        _reach(x.right, fn, mod, R, seen)
        return
    if isinstance(x, ast.DictComp):
        _reach(x.key, fn, mod, R, seen)
        _reach(x.value, fn, mod, R, seen)
        for g in x.generators:
            _reach(g.iter, fn, mod, R, seen)
        return
    if isinstance(x, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
        _reach(x.elt, fn, mod, R, seen)
        if not (DICT_PARTS and _STRICT[0] == 0):  # DICT_PARTS: the element's targets carry their part
            for g in x.generators:
                _reach(g.iter, fn, mod, R, seen)
        return
    if isinstance(x, ast.Subscript):
        if DICT_PARTS and _STRICT[0] == 0:
            _reach_part(x.value, "values", fn, mod, R, seen)
        else:
            _reach(x.value, fn, mod, R, seen)
        return
    if isinstance(x, ast.Starred):
        _reach(x.value, fn, mod, R, seen)
        return
    if isinstance(x, ast.Name):
        if PARAM and fn is not None and (id(fn), x.id) in _PSTACK:
            R.open.append((OPEN_PARAM, "a cycle through %s.%s(%s)" % (mod, fn.name, x.id)))
            return
        _bound = _CALLCTX.get((id(fn), x.id)) if fn is not None else None
        key = ("name", id(fn), x.id) + ((_bound[4],) if _bound else ())
        if key in seen:
            R.revisit = True
            return
        if _bound is not None:                    # a parameter bound to the call being reached
            seen.add(key)
            arg, afn, amod, why = _bound[:4]
            if why:
                R.open.append((OPEN_PARAM, why))
            else:
                _reach(arg, afn, amod, R, seen)
            return
        seen.add(key)
        comp = [n for n in (own(fn) if fn is not None else []) if isinstance(n, ast.comprehension)]
        if fn is not None and x.id in params(fn):
            if not PARAM:
                R.open.append((OPEN_PARAM, x.id))
                return
            args, fails_ = param_calls(fn, mod, x.id)
            if not args and not fails_:
                R.open.append((OPEN_PARAM, "no call of %s.%s in the read modules passes %s, and it has no default"
                               % (mod, fn.name, x.id)))
                return
            for msg in fails_:
                R.open.append((OPEN_PARAM, msg))
            if len(_PSTACK) >= 3:
                R.open.append((OPEN_PARAM, "a chain deeper than 3 at %s.%s" % (mod, fn.name)))
                return
            _PSTACK.append((id(fn), x.id))
            try:
                for cmod, cfn, a in args:
                    sub = Reach()
                    _reach(a, cfn, cmod, sub, seen)
                    if not (sub.consts or sub.open or sub.proved or sub.revisit):
                        R.open.append((OPEN_PARAM, "the argument at %s.%s:%d reaches nothing" % (
                            cmod, cfn.name if cfn is not None else "<module>", getattr(a, "lineno", 0))))
                    for c in sub.consts:
                        R.add_const(c)
                    if sub.open:
                        R.open.append((OPEN_PARAM, "a caller the resolver cannot read: %s.%s:%d (%s)" % (
                            cmod, cfn.name if cfn is not None else "<module>", getattr(a, "lineno", 0),
                            sub.open[0][1])))
            finally:
                _PSTACK.pop()
            return
        vals = fn_bindings(fn, x.id) if fn is not None else []
        vals += bindings_in(comp, x.id) if not vals else []
        if vals and MUTATION and any(isinstance(v, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp,
                                                         ast.SetComp)) for v in vals):
            for msg in passed_unread(own_list(fn), mod, x.id):
                R.open.append((OPEN_MUTATION, msg))
        if vals:
            # condition (c): a comprehension's target is its own scope, so only bindings outside
            # comprehensions count toward 'one binding in its function'
            strict = len(bindings_in([n for n in own_list(fn) if not isinstance(n, ast.comprehension)],
                                     x.id)) > 1
            _STRICT[0] += strict
            try:
                for v in vals:
                    _reach(v, fn, mod, R, seen)
            finally:
                _STRICT[0] -= strict
            return
        mvals, imp = module_bindings(mod, x.id)
        if mvals and MUTATION and any(isinstance(v, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp,
                                                          ast.SetComp)) for v in mvals):
            for item in global_mutations(mod, x.id):
                if item[0] == "MOD":
                    _reach(item[2], None, item[1], R, seen)
                else:
                    _reach(item[1], item[0], mod, R, seen)
            if (mod, x.id) not in _PMOD:
                if mod not in _ALLN:
                    _ALLN[mod] = [c for c in ast.walk(trees[mod]) if isinstance(c, ast.Call)]
                _PMOD[(mod, x.id)] = passed_unread(_ALLN[mod], mod, x.id)
            for msg in _PMOD[(mod, x.id)]:
                R.open.append((OPEN_MUTATION, msg))
        if mvals:
            for v in mvals:
                _reach(v, None, mod, R, seen)
            return
        if imp is not None and imp[0] in trees:
            iv, _ = module_bindings(imp[0], imp[1])
            if iv:
                for v in iv:
                    _reach(v, None, imp[0], R, seen)
                return
        R.open.append((OPEN_UNBOUND, x.id))
        return
    if isinstance(x, ast.Attribute):
        if isinstance(x.value, ast.Name) and (x.value.id in ALIASES[mod] or x.value.id in trees):
            m2 = ALIASES[mod].get(x.value.id, x.value.id)
            iv, _ = module_bindings(m2, x.attr)
            if iv:
                for v in iv:
                    _reach(v, None, m2, R, seen)
                return
        R.open.append((OPEN_ATTR, ast.unparse(x)[:60]))
        return
    if isinstance(x, ast.Call):
        f = x.func
        if isinstance(f, ast.Attribute) and f.attr in STR_METHODS:
            _reach(f.value, fn, mod, R, seen)
            for a in list(x.args) + [k.value for k in x.keywords]:
                _reach(a, fn, mod, R, seen)
            return
        if DICT_PARTS and _STRICT[0] == 0 and isinstance(f, ast.Attribute) and f.attr in ("values", "keys", "get"):
            _reach_part(f.value, "keys" if f.attr == "keys" else "values", fn, mod, R, seen)
            for a in x.args[1:]:
                _reach(a, fn, mod, R, seen)
            return
        if isinstance(f, ast.Attribute) and f.attr in ("items", "values", "keys", "get", "copy"):
            _reach(f.value, fn, mod, R, seen)
            for a in x.args[1:]:
                _reach(a, fn, mod, R, seen)
            return
        if isinstance(f, ast.Name) and f.id in ("str", "sorted", "list", "tuple", "set", "reversed", "enumerate",
                                                "zip", "dict"):
            for a in x.args:
                _reach(a, fn, mod, R, seen)
            return
        if isinstance(f, ast.Name) and f.id == "range":
            R.proved = True
            return
        if isinstance(f, ast.Name) and f.id in _sqla_text(mod):
            for a in x.args:                     # sqlalchemy's text(): the text it is given
                _reach(a, fn, mod, R, seen)
            return
        targets = _call_targets(x, fn, mod)
        if targets:
            for m2, d in targets:
                cs, op = fn_closure_consts(m2, d)
                for c in cs:
                    R.add_const(c)
                R.open += op
                _reach_returns(m2, d, R, seen, x, fn, mod)
            return
        R.open.append((OPEN_CALL, ast.unparse(f)[:60]))
        return
    R.open.append((OPEN_OTHER, type(x).__name__))


def _sqla_text(mod):
    """the module-level names under which mod imports sqlalchemy's text."""
    if mod not in _SQLA_TEXT:
        _SQLA_TEXT[mod] = {a.asname or a.name for st in trees[mod].body if isinstance(st, ast.ImportFrom)
                           and st.module in ("sqlalchemy", "sqlalchemy.sql") for a in st.names if a.name == "text"}
    return _SQLA_TEXT[mod]


_SQLA_TEXT = {}


_CALLCTX = {}          # (id(def), parameter) -> (argument expression or None, its def, its module, why)


def _call_targets(call, fn, mod):
    """[(module, def)] of the read functions a call can reach: a def of that name nested in fn, else what the
    index resolves; None when it reaches none."""
    f = call.func
    targets = None
    if fn is not None and isinstance(f, ast.Name):
        local = [n for n in ast.walk(fn) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name == f.id and n is not fn]
        targets = [(mod, n) for n in local] or None
    return targets or resolve_call(mod, f)


def _pos_returns(d, n):
    """R1: the return statements of d's own body when every one that has a value is a tuple display of
    exactly n elements, none starred, and d does not yield; else None (the rule does not apply)."""
    body = list(own(d))
    if any(isinstance(x, (ast.Yield, ast.YieldFrom)) for x in body):
        return None
    rets = [x.value for x in body if isinstance(x, ast.Return) and x.value is not None]
    if not rets or not all(isinstance(r, ast.Tuple) and len(r.elts) == n
                           and not any(isinstance(e, ast.Starred) for e in r.elts) for r in rets):
        return None
    return rets


_PARENTS = {}


def _enclosing_comps(mod, node):
    """the comprehension clauses around node, up to its def (R2 reads a starred name with them in view)."""
    if mod not in _PARENTS:
        _PARENTS[mod] = {id(c): p for p in ast.walk(trees[mod]) for c in ast.iter_child_nodes(p)}
    up, out, cur = _PARENTS[mod], [], node
    while id(cur) in up:
        cur = up[id(cur)]
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            break
        if isinstance(cur, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            out += list(cur.generators)
    return out


def _call_bindings(d, call, cfn, cmod, dmod):
    """the parameters of d bound to this call: positional and keyword arguments, then the defaults; a star
    argument binds nothing (every parameter is then open); a parameter left without a value is open."""
    a = d.args
    pos = [x.arg for x in a.posonlyargs + a.args]
    names = pos + [x.arg for x in a.kwonlyargs] + [x.arg for x in (a.vararg, a.kwarg) if x is not None]
    out = {}
    stars = [i for i, x in enumerate(call.args) if isinstance(x, ast.Starred)]
    if any(k.arg is None for k in call.keywords) or len(stars) > 1 or (stars and stars[0] != len(call.args) - 1):
        return {n: (None, None, None, "a star argument at %s:%d" % (cmod, call.lineno)) for n in names}
    k0 = stars[0] if stars else len(call.args)
    for i, v in enumerate(call.args[:k0]):
        if i < len(pos):
            out[pos[i]] = (v, cfn, cmod, None)
    if stars:                                     # R2: the star fills every positional from its place on
        star = ("STAR", call.args[k0].value, _enclosing_comps(cmod, call)) if cmod in trees else None
        for n in pos[k0:] + ([a.vararg.arg] if a.vararg else []):
            out[n] = (star, cfn, cmod, None if star is not None else "a star argument at %s:%d" % (cmod, call.lineno))
    for k in call.keywords:
        out[k.arg] = (k.value, cfn, cmod, None)
    defaults = dict(zip(pos[len(pos) - len(a.defaults):], a.defaults)) if a.defaults else {}
    defaults.update({k.arg: dv for k, dv in zip(a.kwonlyargs, a.kw_defaults) if dv is not None})
    for n in names:
        if n not in out:
            out[n] = (defaults[n], None, dmod, None) if n in defaults else (
                None, None, None, "%s of %s is not passed at %s:%d and has no default" % (n, d.name, cmod, call.lineno))
    return out


def _reach_returns(m2, d, R, seen, call=None, cfn=None, cmod=None):
    """RULING-CENSUS-8 (b): a read function's call reaches its return values (its own body, nested defs left
    out), its parameters bound to this call's arguments (then its defaults); an unread call or attribute is
    open. No return with a value, or a yield, is a closed failure."""
    key = ("ret", id(d), id(call))
    if key in seen:
        R.revisit = True
        return
    seen.add(key)
    body = list(own(d))
    if any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in body):
        R.open.append((OPEN_CALL, "the read function %s.%s yields" % (m2, d.name)))
        return
    rets = [n.value for n in body if isinstance(n, ast.Return) and n.value is not None]
    if not rets:
        R.open.append((OPEN_CALL, "no return with a value in the read function %s.%s" % (m2, d.name)))
        return
    _reach_bound(m2, d, rets, R, seen, call, cfn, cmod)


def _reach_bound(m2, d, exprs, R, seen, call, cfn, cmod):
    """reach each expression of d's body with d's parameters bound to this call (then the defaults)."""
    binds = _call_bindings(d, call, cfn, cmod, m2) if call is not None else {}
    saved = {k: _CALLCTX.get(k) for k in [(id(d), n) for n in binds]}
    for n, b in binds.items():
        _CALLCTX[(id(d), n)] = b + (id(call),)
    try:
        for rv in exprs:
            _reach(rv, d, m2, R, seen)
    finally:
        for k, v in saved.items():
            if v is None:
                _CALLCTX.pop(k, None)
            else:
                _CALLCTX[k] = v


# ---------------------------------------------------------------- classify
RX = re.compile(r"^(\w+)\.(\w+):(\d+): (module name|local name|\w+) (.*)$")
TABLEPOS = re.compile(r"\b(UPDATE|INTO|FROM|JOIN|USING|OF)\s+$", re.I)
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
bylines = {m: defaultdict(list) for m in trees}
for m, t in trees.items():
    for c in ast.walk(t):
        if isinstance(c, ast.Call):
            bylines[m][c.lineno].append(c)


def loop_texts_form(mod, fname, node):
    """ORDER 2's loop form: a Name that is an unpacked loop target over a literal tuple of tuples whose
    elements at its position are texts."""
    if not isinstance(node, ast.Name):
        return None
    for fn in ast.walk(trees[mod]):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == fname:
            for st in ast.walk(fn):
                if isinstance(st, ast.For) and isinstance(st.target, ast.Tuple) and isinstance(st.iter, ast.Tuple):
                    for i, tg in enumerate(st.target.elts):
                        if isinstance(tg, ast.Name) and tg.id == node.id and all(
                                isinstance(r, ast.Tuple) and len(r.elts) == len(st.target.elts)
                                and isinstance(r.elts[i], (ast.Constant, ast.BinOp, ast.JoinedStr))
                                for r in st.iter.elts):
                            out = []
                            for r in st.iter.elts:
                                s = exact_texts(r.elts[i], fn, mod)
                                if s is None:
                                    return ("FAIL", "the loop element %s does not read exactly"
                                            % ast.unparse(r.elts[i])[:60])
                                out += s
                            return sorted(set(out))
    return None


def _vkey(v):
    return repr((tuple(v[:-1]), sorted(v[-1])))


def _digest(items):
    return hashlib.sha256("\x00".join(sorted(items)).encode("utf-8")).hexdigest()


_TYPED = re.compile(r"\{\?t:([^}]*)\}|\{\?d:([^}]*)\}")


def typed_variants(t, cap=512):
    """every text the fragment t can be with its typed holes filled ({?t:a|b} by each alternative, {?d:k} by
    each value the reader holds for k), or None when a dict hole has no value or the product passes cap."""
    ms = list(_TYPED.finditer(t))
    if not ms:
        return [t]
    choices = []
    for m in ms:
        if m.group(1) is not None:
            choices.append(m.group(1).split("|"))
        else:
            vs = sorted(DICTS.get(m.group(2), ()))
            if not vs:
                return None
            choices.append(vs)
    n = 1
    for c in choices:
        n *= len(c)
    if n > cap:
        return None
    out = []
    for combo in itertools.product(*choices):
        it = iter(combo)
        out.append(_TYPED.sub(lambda _m: next(it), t))
    return out


def expand_count(t):
    n = 0
    for seg in t.split(" ;; "):
        k = 1
        for m in re.finditer(r"\{\?t:([^}]*)\}", seg):
            k *= len(m.group(1).split("|"))
        for m in re.finditer(r"\{\?d:([^}]*)\}", seg):
            k *= max(1, len(DICTS.get(m.group(1), ())))
        n += k
    return n


HOLE_CONSTS = {}
rows = []
closed_sets = {"open_d": []}
for f in fails:
    m = RX.match(f)
    mod, fname, line, form, expr = m.group(1), m.group(2), int(m.group(3)), m.group(4), m.group(5)
    node = None
    for c in bylines[mod][line]:
        if c.args:
            a = B.statement_argument(c) if not (isinstance(c.func, ast.Name) and c.func.id == "text") else c.args[0]
            if a is not None and repr(ast.unparse(a)[:80]) == expr:
                node = a
                break
    rec = {"place": f, "module": mod, "form": form}
    _JUDGED_USE.clear()
    lt = loop_texts_form(mod, fname, node) if node is not None else None
    key = None if node is None else (mod, node.lineno, node.col_offset)
    if key is not None and key not in REC and mod in src.trees:
        for n in [n for n in names if n == mc.qn(mod, fname) or n.startswith(mod + ":") and (
                n.endswith(":" + fname) or n.endswith("." + fname)) or mod == "main" and n.endswith("." + fname)]:
            try:
                src.events(n)
            except Exception as ex:  # noqa: BLE001
                rec.setdefault("events_fail", []).append("%s %s" % (n, type(ex).__name__))
    got = REC.get(key, []) if key else []
    if form in ("module name", "local name") and node is not None and form == "module name":
        mv, imp = module_bindings(mod, node.id)
        rec["bound_to"] = [("<no value>" if v is None else ("<loop>" if isinstance(v, tuple) else ast.unparse(v)[:120]))
                           for v in mv] + ([("import", imp)] if imp else [])
    if (VALUE or PARAM) and not lt and node is not None and got and any(g is None for g in got) \
            and mod in src.trees:
        _n = len(HOLES)
        HOLES[_n] = (node, ("DEF", enclosing_def(mod, node)), mod)
        got = ["{?}\x01%d\x02" % _n]
        rec["whole_argument"] = True
    _whole_exact = None
    if VALUE and not lt and node is not None and mod in src.trees:
        _whole_exact = exact_texts(node, enclosing_def(mod, node), mod)
    if isinstance(lt, list) and not lt:
        rec.update(verdict="remaining", cause="an empty exact reading: the loop form reads no text")
    elif isinstance(lt, tuple):
        rec.update(verdict="remaining", cause=lt[1])
    elif lt:
        rec.update(verdict="read", how="loop texts (ORDER 2)", texts=len(lt))
        rec["verdict_set"] = sorted({_vkey(verdicts(x)) for x in lt})
    elif _whole_exact is not None and not _whole_exact:
        rec.update(verdict="remaining", cause="an empty exact reading at the place")
    elif _whole_exact is not None:
        rec.update(verdict="expanded" if len(_whole_exact) > 1 else "read", how="exact at the place (VALUE)",
                   texts=len(_whole_exact), exact_digest=__import__("hashlib").sha256(
                       "\x00".join(_whole_exact).encode("utf-8")).hexdigest()[:16])
        rec["verdict_set"] = sorted({_vkey(verdicts(x)) for x in _whole_exact})
    elif mod not in src.trees:
        rec.update(verdict="remaining", cause="unread: module not read by the deletion census")
    elif node is None:
        rec.update(verdict="remaining", cause="unread: argument not located")
    elif not got:
        rec.update(verdict="remaining", cause="unread: not reached")
    elif any(g is None for g in got):
        rec.update(verdict="remaining", cause="unread")
    else:
        texts = sorted(set(got))
        rec["read_part"] = [MK.sub("", t)[:400] for t in texts]
        holes = sorted({int(n) for t in texts for n in MK.findall(t)})
        typed = any(re.search(r"\{\?[td]:", t) or " ;; " in t for t in texts)
        for t in texts:
            for d in re.findall(r"\{\?d:([^}]*)\}", t):
                if not DICTS.get(d):
                    closed_sets["open_d"].append((f, d))
        open_d = sorted({d for t in texts for d in re.findall(r"\{\?d:([^}]*)\}", t) if not DICTS.get(d)})
        if open_d:
            rec.update(verdict="remaining", cause="typed hole with no closed value set", causes=[
                ("typed hole with no closed value set", d) for d in open_d])
        elif not holes:
            _tv = [typed_variants(alt) for x in texts for alt in x.split(" ;; ")]
            if any(v is None for v in _tv):
                rec.update(verdict="remaining", cause="a typed hole with no value, or over 512 texts")
            else:
                rec.update(verdict="expanded" if typed else "read", texts=sum(expand_count(t) for t in texts))
                rec["verdict_set"] = sorted({_vkey(verdicts(v)) for vs in _tv for v in vs})
        else:
            causes, hole_info, widest_parts = [], {}, {}
            EXP = {}
            for n in holes:
                hn, hfn, hmod = HOLES[n]
                fn, _map_why = (hfn[1], None) if isinstance(hfn, tuple) else as_trees_def(hmod, fnode(hfn)) \
                    if hfn else (None, None)
                if _map_why:
                    causes.append(("def map", _map_why))
                ev = exact_texts(hn, fn, hmod) if (VALUE or PARAM) else None
                if ev is None and EXPANSION:
                    ev = expansion_values(hn, fn, hmod)
                if ev is not None and not ev:
                    causes.append(("an empty exact reading", "the hole %s reads no text" % ast.unparse(hn)[:60]))
                if ev is not None:
                    EXP[n] = ev
                    hole_info[n] = (ast.unparse(hn)[:80], [], [], False)
                    HOLE_CONSTS[n] = set()
                    widest_parts[n] = ""
                    continue
                R = reach(hn, fn, hmod)
                if not (R.consts or R.open or R.proved):
                    causes.append(("an empty reach", "nothing reaches the hole %s" % ast.unparse(hn)[:60]))
                hole_info[n] = (ast.unparse(hn)[:80], sorted(R.consts)[:40], R.open, R.number and not R.open)
                for kind, what in R.open:
                    causes.append((kind, what))
                for c in R.consts:
                    if LOCK_RX.search(c):
                        causes.append(("lock word in a reaching constant", c[:60]))
                widest_parts[n] = " ".join(sorted(R.consts)) if R.consts else "0"
                HOLE_CONSTS[n] = set(R.consts)
            typed_tp = set()
            for t in texts:
                for mm in MK.finditer(t):
                    n = int(mm.group(1))
                    consts = hole_info[n][1]
                    if TABLEPOS.search(MK.sub("", t[:mm.start()])) and consts and not hole_info[n][2]                             and all(IDENT.fullmatch(c) for c in HOLE_CONSTS[n]):
                        typed_tp.add(n)
            n_texts = 0
            _vset, _wide_tables = set(), set()
            for t in texts:
                tn = sorted({int(x) for x in MK.findall(t)} & (typed_tp | set(EXP)))
                vsets = [EXP[n] if n in EXP else sorted(HOLE_CONSTS[n]) for n in tn]
                _p = 1
                for _v in vsets:
                    _p *= len(_v)
                if EXP and _p > 64:
                    causes.append(("expansion over 64 texts", str([len(_v) for _v in vsets])))
                for combo in itertools.islice(itertools.product(*vsets), 512):
                    sub = dict(zip(tn, combo))
                    e = MK.sub(lambda mm: sub[int(mm.group(1))] if int(mm.group(1)) in sub else mm.group(0), t)
                    n_texts += expand_count(MK.sub("", e))
                    blanked = MK.sub("", e)
                    wide = MK.sub(lambda mm: " " + widest_parts[int(mm.group(1))] + " ", e)
                    _bv, _wv = typed_variants(blanked), typed_variants(wide)
                    if _bv is None or _wv is None or len(_bv) != len(_wv):
                        causes.append(("a typed hole with no value, or over 512 texts", blanked[:60]))
                        _bv, _wv = [blanked], [wide]
                    lockread = any(LOCK_RX.search(_b) for _b in _bv)
                    for mm in MK.finditer(e):
                        n = int(mm.group(1))
                        before = MK.sub("", e[:mm.start()])
                        if lockread and TABLEPOS.search(before):
                            causes.append(("table position", "%s after %r" % (hole_info[n][0], before[-30:])))
                        depth_open = before.lower().rfind("pg_advisory")
                        if lockread and depth_open >= 0 and before[depth_open:].count("(") > before[depth_open:].count(")"):
                            causes.append(("inside an advisory call", hole_info[n][0]))
                    for _b, _w in zip(_bv, _wv):
                        _vset.add(_vkey(verdicts(_b)))
                        _wide_tables |= set(verdicts(_w)[-1])
                        if verdicts(_b) != verdicts(_w):
                            causes.append(("the verdicts differ", "%s vs %s" % (verdicts(_b), verdicts(_w))))
            rec["holes"] = {str(k): v for k, v in hole_info.items()}
            rec["verdict_set"] = sorted(_vset)
            rec["widest_tables"] = sorted(_wide_tables)
            rec["reach_digest"] = _digest(set().union(*[HOLE_CONSTS.get(n, set()) for n in holes]))
            rec["typed_table_holes"] = sorted(typed_tp)
            causes = [c for c in causes if not (c[0] == "lock word in a reaching constant" and False)]
            if causes:
                rec.update(verdict="remaining", cause=causes[0][0], causes=causes)
            elif set(holes) <= typed_tp | set(EXP):
                rec.update(verdict="expanded", texts=n_texts,
                           how="whole values of a display (section 3)" if EXP else "typed table-position hole")
            else:
                rec.update(verdict="bounded", texts=n_texts)
    if _JUDGED_USE and rec.get("verdict") in ("read", "expanded"):
        rec["exact_verdict"] = rec["verdict"]
        rec.update(verdict="judged", judged_values=sorted(set(_JUDGED_USE)))
    rows.append(rec)

mc.Source.text = _orig          # the reader's patch ends with the run

# The limits of this resolver, each a sentence that can be shown false (RULING-CENSUS-3 (f), RULING-CENSUS-4
# sections 5 and 7, RULING-CENSUS-5 section 6, RULING-CENSUS-6 section 2 (d)).
LIMITS = (
    "A word split across two constants is not seen: the lock and table words are matched in each reaching "
    "constant alone.",
    "Lock words and table words are matched without regard to case, as the verdict patterns match them.",
    "Callers outside backend/api are not read: a parameter is read through the calls of its function in "
    "the read modules alone.",
    "A read of a regex's .pattern changes nothing: the reach has no rule that leaves a pattern out.",
    "A method on a local receiver passes by name; false if a read function calls a same-named method of "
    "another type whose result reaches a statement text.",
    "A store into a container after its binding (append, extend, insert, +=, a subscript store, update, "
    "setdefault, add) is a binding of it, and a container passed whole to a call the form does not read is "
    "not closed.",
)
