"""The no-tunables guard for the public review code.

The public review code describes evidence and evaluates rules generically;
every value that decides an outcome belongs to the rules revision, which is
not part of this repository. This guard checks that, as a transitive analysis
over the source of every tree it is given:

  * JUDGING modules (review_measures, review_rules, and any local module
    one of them imports) are
    scanned whole: code, module-level constants, string constants (SQL and
    text included) and comments;
  * seat_evidence is scanned from its REVIEW ROOTS (every function that
    touches the review modules or a loaded ruleset) through every module
    -level function and constant they reach, and main.py from its review
    worker functions the same way; any local module either imports is
    followed and scanned whole.

Within that reach it refuses:
  number   a numeric constant (after folding constant arithmetic) unless its
           CONTEXT makes it structural (STRUCTURAL below: a subscript index
           or slice bound on a computed value; 0 in any comparison and 1 or -1
           only in an equality test; a step of 1, a halving, a millisecond
           conversion or an integer wrap in arithmetic; 0, 1, -1 or 2 as a
           call argument; 0, 1 or -1 anywhere else) or it sits inside a
           PINNED contract bound whose value matches. A structural value used
           as a threshold (`x > 2`, `x * 2 > y`) is therefore refused;
  select   a string constant compared against a value (==, !=, in, not in,
           including the members of a literal collection on the right of
           `in`) that is not one of the closed public SELECTORS, so a new
           kind, label or category cannot decide anything unseen;
  bool     a module-level True/False binding that is not PINNED, a
           comparison against True or False other than the three-valued
           identity test (`is True`, `is False`), and a True/False constant as an
           if, while-else, conditional-expression or boolean-operator operand
           (`while True:` is the one structural form);
  text     a digit inside a string constant or comment, other than a
           standalone 0 or 1 and the closed set of identifiers that carry one;
  call     a value decoded from a constant (int/float/Decimal/json of a
           constant string, len of a constant) and the dynamic forms
           (eval, exec, compile, chr, ord, getattr/globals/vars, base64,
           codecs, importlib, __import__, bytes.fromhex);
  setting  a runtime setting read other than the operational switches, or
           the settings table named outside the one reader;
  env      an environment read other than the allowlisted keys;
  pinned   a pinned bound whose value differs from its pin.

Every value above is judged WHERE IT IS USED, following its binding within
the module: a constant assigned once to a name (module level or function
local) and used later, a class attribute (`self.X`, `cls.X`, `Klass.X`), a
value of a literal dict (`D["k"]`), a parameter default, and a function whose
every return is one constant (`f()`) each stand for their value at the use, so
`LIMIT = 1` ... `x > LIMIT` is judged as `x > 1`, `strict = True` ... `if
strict:` as `if True:`, and `KIND = "k"` ... `x == KIND` as `x == "k"`. A
parameter default is followed only when it is a boolean. A
PINNED name is judged by its pin, not at its uses; a name bound more than once
(a counter, a loop variable) is not a constant.

Modes:
  python backend/tools/review_guard.py tree <repo dir>
  python backend/tools/review_guard.py range <repo dir> <base> <tip>
        every commit of base..tip, each tree checked on its own (a value
        that lived only in an earlier commit is still in the landing range)

Output: one line per finding, `<commit|tree> <path>:<line> <class>` (never
the offending text), then `review_guard: <n> finding(s) in <m> tree(s)`.
Exit 0 clean, 1 findings, 2 usage or a tree that could not be read.
"""

from __future__ import annotations

import ast
import io
import os
import re
import subprocess
import sys
import tokenize

API = "backend/api/"
JUDGING = ("review_measures", "review_rules")
ROOTED = {"seat_evidence": None, "main": ("review_worker_loop", "review_worker_pass",
                                          "review_rules_refresh_loop", "_review_pass_line")}
REVIEW_NAMES = {"rm", "rr", "_review_rules", "review_measures", "review_rules"}
REVIEW_PARAMS = {"rs", "state", "ruleset"}
# Plumbing a rooted function may import without it being followed: the
# session factory and the table declarations decide nothing.
INFRA = {"database", "models"}

INDEX_MAX = 15
# Structural numbers BY CONTEXT (see the module docstring). No value is
# allowed everywhere; each context names what it admits.
STRUCTURAL = {
    "compare_any": {0},
    "compare_eq": {0, 1, -1},
    "binop": {(ast.Add, 1), (ast.Sub, 1), (ast.Add, -1), (ast.Sub, -1),
              (ast.FloorDiv, 2), (ast.Mod, 2),
              (ast.Mult, 1000), (ast.Div, 1000), (ast.FloorDiv, 1000)},
    "wrap": {2 ** 31, 2 ** 32},
    "augassign": {1, -1},
    "call": {0, 1, -1, 2},
    "plain": {0, 1, -1},
}
_EQ_OPS = (ast.Eq, ast.NotEq, ast.Is, ast.IsNot)
_SEL_OPS = (ast.Eq, ast.NotEq, ast.In, ast.NotIn)
# The closed public selectors: every string a reached function compares a
# value against. Contract words only (record fields, rule scopes and effects,
# loader words, health words, file names of the public format). A string
# outside this set in a comparison is refused.
SELECTORS = frozenset({
    "1", "REVISION", "__main__", "__pycache__", "abs", "absent", "add", "all", "any", "b",
    "build", "core.game", "data", "dirty", "edges", "eq", "expr", "filters", "flag", "game",
    "ge", "gt", "honoured", "int", "json", "label", "le", "list", "literal", "lt", "m",
    "missing", "ne", "not", "note", "nt", "num", "open", "params", "pointer", "posix",
    "post_rows", "read", "refused", "rel", "reporter", "row", "rules-none", "seat", "side",
    "sitting",
    "sub", "unhonoured", "v", "validate", "window_days", "{", "}"})

# Contract bounds and scheduling: pinned BY VALUE. A deciding value added to
# one of these makes the pin differ, and the guard refuses it.
PINNED = {
    ("review_measures", "CONTRACT_BOUNDS"): {"ready_lag_s": 120, "edges_max": 8, "label_max": 16,
                                             "show_max": 16, "eval_hex": 8},
    ("review_measures", "WINDOW_KINDS"): (0, 2, 3),
    ("review_rules", "CONTRACT_BOUNDS"): {
        "files_max": 64, "total_bytes_max": 16777216, "rules_bytes_max": 1048576,
        "selftest_bytes_max": 4194304, "data_bytes_max": 8388608, "rules_max": 200,
        "pred_depth_max": 6, "cases_max": 256, "work_max": 200000, "deadline_s": 10,
        "line_max": 400, "places_default": 3, "round_places": 4, "render_items_max": 6,
        "id_hex": 8, "rev_hex": 12, "nonce_bytes": 16, "digest_hex": 64, "data_name_max": 40,
        "pointer_bytes_max": 64, "frame_bytes": 8, "format": 1},
    ("review_rules", "_NT"): {"read": 0x80000000, "share": 0x7, "existing": 3,
                              "no_follow": 0x00200000, "buffer": 32768},
    ("seat_evidence", "SEATS"): 2,
    ("review_measures", "SEATS"): 2,
    ("review_rules", "PAIR"): 2,
    ("review_rules", "EXIT_USAGE"): 2,
    ("seat_evidence", "GAME_EXPIRY_DAYS"): 14,
    ("seat_evidence", "GAMES_PER_PASS"): 500,
    ("seat_evidence", "SITTINGS_PER_PASS"): 500,
    ("seat_evidence", "MARK_ROWS_PER_PASS"): 5000,
    ("seat_evidence", "DETAILS_MAX_BYTES"): 2048,
    ("seat_evidence", "COMPAT_ROWS_SHOWN"): 10,
    ("main", "REVIEW_PASS_S"): 600,
    ("main", "REVIEW_FIRST_PASS_S"): 90,
    ("main", "REVIEW_PURGE_EVERY_S"): 72000,
    ("main", "REVIEW_REFRESH_S"): 60,
}
SWITCHES = {"seat_evidence_accept", "seat_evidence_worker", "seat_evidence_purge"}
SETTINGS_READER = ("seat_evidence", "setting")
ENV_KEYS = {"SCR_REVIEW_ROOT", "SYSTEMROOT"}

# Identifiers that carry a digit and decide nothing: match-row columns of the
# two seats, their SQL aliases, digest and encoding names, the Windows
# system library the non-following open calls.
_SAFE_TEXT = re.compile(
    r"\bp[12]_\w+|\bplayer[12](?:_id)?\b|\b[ps][12]\b|sha256\b|\butf-8\b|\bint(?:32|64)\b"
    r"|\bkernel32\b"
    r"|\bnoqa: ?[A-Z]+\d+(?:, ?[A-Z]+\d+)*")
_STANDALONE = re.compile(r"(?<![\w.])[01](?![\w.])")
_DIGIT = re.compile(r"\d")

_DYNAMIC_CALLS = {"eval", "exec", "compile", "chr", "ord", "getattr", "globals", "vars",
                  "__import__", "setattr", "locals"}
_DYNAMIC_MODULES = {"base64", "codecs", "importlib", "binascii", "pickle", "marshal", "zlib"}
_DECODERS = {"int", "float", "Decimal", "complex", "len", "loads", "literal_eval", "fromhex"}


def text_bad(s: str) -> bool:
    s = _SAFE_TEXT.sub(" ", s)
    s = _STANDALONE.sub(" ", s)
    return bool(_DIGIT.search(s))


def _fold(node):
    """The value of a constant numeric expression, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _fold(node.operand)
        return None if v is None else (-v if isinstance(node.op, ast.USub) else v)
    if isinstance(node, ast.BinOp):
        a, b = _fold(node.left), _fold(node.right)
        if a is None or b is None:
            return None
        try:
            return {ast.Add: lambda: a + b, ast.Sub: lambda: a - b, ast.Mult: lambda: a * b,
                    ast.Pow: lambda: a ** b, ast.FloorDiv: lambda: a // b,
                    ast.Div: lambda: a / b, ast.Mod: lambda: a % b}[type(node.op)]()
        except (KeyError, ArithmeticError):
            return None
    return None


class _Scan:
    def __init__(self, modname, label, src):
        self.mod = modname
        self.label = label
        self.src = src
        self.tree = ast.parse(src)
        self.findings = []
        self.defs = {}
        self.assigns = {}
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.defs[node.name] = node
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Name):
                        self.assigns[t.id] = node
        self.str_consts = {}
        for name, node in self.assigns.items():
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                self.str_consts[name] = node.value.value
        self._bind_module()

    # -- bindings followed to their uses --
    _NONE = object()

    @staticmethod
    def _constlike(v):
        """The value of a constant expression: a number (folded), a string, a
        boolean, or a literal dict of string keys to such values."""
        if v is None:
            return _Scan._NONE
        n = _fold(v)
        if n is not None:
            return n
        if isinstance(v, ast.Constant) and isinstance(v.value, (str, bool)):
            return v.value
        if isinstance(v, ast.Dict) and v.keys and all(
                isinstance(k, ast.Constant) and isinstance(k.value, str) for k in v.keys):
            vals = [_Scan._constlike(x) for x in v.values]
            if all(x is not _Scan._NONE and not isinstance(x, dict) for x in vals):
                return {k.value: x for k, x in zip(v.keys, vals)}
        return _Scan._NONE

    @staticmethod
    def _stores(nodes):
        """name -> number of times the statements bind it (assignment,
        augmented assignment, loop or with target, import, def, parameter)."""
        out = {}

        def hit(n):
            out[n] = out.get(n, 0) + 1
        for top in nodes:
            for n in ast.walk(top):
                if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                    hit(n.id)
                elif isinstance(n, ast.arg):
                    hit(n.arg)
                elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    hit(n.name)
                elif isinstance(n, (ast.Import, ast.ImportFrom)):
                    for a in n.names:
                        hit((a.asname or a.name).split(".")[0])
        return out

    def _bind_module(self):
        top_stores = {}
        for node in self.tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                for k, c in self._stores([node]).items():
                    top_stores[k] = top_stores.get(k, 0) + c
        self.module_consts = {}
        for name, node in self.assigns.items():
            if (self.mod, name) in PINNED or top_stores.get(name, 0) != 1:
                continue
            v = self._constlike(node.value)
            if v is not self._NONE:
                self.module_consts[name] = v
        self.class_consts = {}
        clash = set()
        for node in self.tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            body_stores = self._stores([s for s in node.body
                                        if isinstance(s, (ast.Assign, ast.AnnAssign, ast.AugAssign))])
            for s in node.body:
                if isinstance(s, ast.Assign) and len(s.targets) == 1 and isinstance(s.targets[0], ast.Name):
                    name = s.targets[0].id
                    v = self._constlike(s.value)
                    if v is self._NONE or body_stores.get(name, 0) != 1:
                        continue
                    if name in self.class_consts and self.class_consts[name] != v:
                        clash.add(name)
                    self.class_consts[name] = v
        for name in clash:
            del self.class_consts[name]
        self.class_names = {n.name for n in self.tree.body if isinstance(n, ast.ClassDef)}
        self.ret_consts = {}
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                rets = [r for r in self._own(node) if isinstance(r, ast.Return)]
                vals = [self._constlike(r.value) for r in rets]
                if vals and all(x is not self._NONE and not isinstance(x, dict) for x in vals) \
                        and all(x == vals[0] and type(x) is type(vals[0]) for x in vals):
                    self.ret_consts[node.name] = vals[0]
        self._locals_cache = {}

    @staticmethod
    def _own(fn):
        """The nodes of a function's own body (not of a nested def or lambda)."""
        out, todo = [], list(fn.body)
        while todo:
            n = todo.pop()
            out.append(n)
            for c in ast.iter_child_nodes(n):
                if not isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                    todo.append(c)
        return out

    def _locals(self, fn):
        """(constants, every bound name) of one function: a local assigned once
        to a constant, or a parameter with a BOOLEAN default never rebound in
        the body (a switch whose default decides a branch; a number default is
        a starting value every caller may move, not a decision)."""
        if id(fn) in self._locals_cache:
            return self._locals_cache[id(fn)]
        own = self._own(fn)
        stores = self._stores([n for n in own if isinstance(n, ast.stmt)] + [fn.args])
        consts = {}
        for n in own:
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                name = n.targets[0].id
                v = self._constlike(n.value)
                if v is not self._NONE and stores.get(name, 0) == 1:
                    consts[name] = v
        a = fn.args
        pos = a.posonlyargs + a.args
        for arg, d in list(zip(pos[len(pos) - len(a.defaults):], a.defaults)) + \
                list(zip(a.kwonlyargs, a.kw_defaults)):
            v = self._constlike(d)
            if isinstance(v, bool) and stores.get(arg.arg, 0) == 1:
                consts[arg.arg] = v
        out = (consts, set(stores))
        self._locals_cache[id(fn)] = out
        return out

    def _enclosing_fns(self, node, parents):
        p = parents.get(id(node))
        out = []
        while p is not None:
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                out.append(p)
            p = parents.get(id(p))
        return out

    def resolve(self, node, parents):
        """The constant a Load of a name, attribute, dict entry or constant
        function stands for here, or _NONE."""
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            for fn in self._enclosing_fns(node, parents):
                if isinstance(fn, ast.Lambda):
                    if node.id in {x.arg for x in fn.args.args}:
                        return self._NONE
                    continue
                consts, bound = self._locals(fn)
                if node.id in consts:
                    return consts[node.id]
                if node.id in bound:
                    return self._NONE
            return self.module_consts.get(node.id, self._NONE)
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load) \
                and isinstance(node.value, ast.Name) \
                and (node.value.id in ("self", "cls") or node.value.id in self.class_names):
            return self.class_consts.get(node.attr, self._NONE)
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) \
                and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            d = self.resolve(node.value, parents)
            if isinstance(d, dict):
                return d.get(node.slice.value, self._NONE)
            return self._NONE
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and not node.args and not node.keywords:
            if any(node.func.id in self._locals(fn)[1] for fn in self._enclosing_fns(node, parents)
                   if not isinstance(fn, ast.Lambda)):
                return self._NONE
            return self.ret_consts.get(node.func.id, self._NONE)
        return self._NONE

    def _alias(self, node, parents):
        """Judge a followed binding at its use."""
        v = self.resolve(node, parents)
        if v is self._NONE or isinstance(v, (dict, str)):
            return                                   # strings: judged in _compare
        p = parents.get(id(node))
        if isinstance(v, bool):
            if (isinstance(p, (ast.If, ast.IfExp, ast.While)) and p.test is node) \
                    or isinstance(p, ast.BoolOp) \
                    or (isinstance(p, ast.UnaryOp) and isinstance(p.op, ast.Not)):
                self.add(node.lineno, "bool")
            elif isinstance(p, ast.Compare):
                ops = p.ops
                if not all(isinstance(o, (ast.Is, ast.IsNot)) for o in ops):
                    self.add(node.lineno, "bool")
            return
        if isinstance(p, ast.Subscript) and p.slice is node and isinstance(v, int) \
                and -1 <= v <= INDEX_MAX:
            return
        if not self._number_ok(v, node, parents):
            self.add(node.lineno, "number")

    def add(self, line, cls):
        self.findings.append((self.label, line, cls))

    # -- the node checks --
    def check_nodes(self, nodes, pinned_ok=frozenset()):
        for top in nodes:
            pinned_node = None
            if isinstance(top, (ast.Assign, ast.AnnAssign)):
                targets = top.targets if isinstance(top, ast.Assign) else [top.target]
                names = [t.id for t in targets if isinstance(t, ast.Name)]
                for n in names:
                    if (self.mod, n) in PINNED:
                        pinned_node = top.value
                        try:
                            val = ast.literal_eval(top.value)
                        except ValueError:
                            val = _fold(top.value)
                        if val != PINNED[(self.mod, n)]:
                            self.add(top.lineno, "pinned")
            self._walk(top, pinned_node)

    def _walk(self, top, pinned_node):
        skip = set()
        if pinned_node is not None:
            skip = {id(n) for n in ast.walk(pinned_node)}
        index_ok = set()
        folded = set()
        parents = {}
        for node in ast.walk(top):
            for child in ast.iter_child_nodes(node):
                parents[id(child)] = node
        for node in ast.walk(top):
            if isinstance(node, ast.Subscript) and not isinstance(node.value, (ast.Constant, ast.List,
                                                                               ast.Tuple, ast.Dict)):
                parts = ([node.slice.lower, node.slice.upper, node.slice.step]
                         if isinstance(node.slice, ast.Slice) else [node.slice])
                for part in parts:
                    v = _fold(part) if part is not None else None
                    if isinstance(v, int) and -1 <= v <= INDEX_MAX:
                        index_ok.update(id(n) for n in ast.walk(part))
        if top is self.tree or isinstance(top, (ast.Assign, ast.AnnAssign)):
            self._module_bool(top)
        for node in ast.walk(top):
            nid = id(node)
            if nid in skip:
                continue
            if isinstance(node, (ast.BinOp, ast.UnaryOp)) and nid not in folded:
                v = _fold(node)
                if v is not None:
                    folded.update(id(n) for n in ast.walk(node))
                    if nid not in index_ok and not self._number_ok(v, node, parents):
                        self.add(node.lineno, "number")
                    continue
            if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript, ast.Call)) \
                    and not isinstance(getattr(node, "ctx", ast.Load()), (ast.Store, ast.Del)):
                self._alias(node, parents)
            if isinstance(node, ast.Compare):
                self._compare(node, parents)
            elif isinstance(node, (ast.If, ast.IfExp, ast.While)):
                t = node.test
                if isinstance(t, ast.Constant) and isinstance(t.value, bool) \
                        and not (isinstance(node, ast.While) and t.value is True and not node.orelse):
                    self.add(node.lineno, "bool")
            elif isinstance(node, ast.BoolOp):
                if any(isinstance(x, ast.Constant) and isinstance(x.value, bool) for x in node.values):
                    self.add(node.lineno, "bool")
            if isinstance(node, ast.Constant):
                if nid in folded:
                    continue
                v = node.value
                if isinstance(v, bool) or v is None:
                    continue
                if isinstance(v, (int, float, complex)):
                    if nid not in index_ok and not self._number_ok(v, node, parents):
                        self.add(node.lineno, "number")
                elif isinstance(v, (str, bytes)):
                    t = v.decode("latin-1") if isinstance(v, bytes) else v
                    if text_bad(t):
                        self.add(node.lineno, "text")
                    if "runtime_settings" in t and (self.mod, self._fn_of(node)) != SETTINGS_READER:
                        self.add(node.lineno, "setting")
            elif isinstance(node, ast.JoinedStr):
                pass  # its literal parts are Constants, checked above
            elif isinstance(node, ast.Call):
                self._call(node)
            elif isinstance(node, ast.Subscript):
                self._env_subscript(node)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                        else [node.module or ""])
                for m in mods:
                    if m.split(".")[0] in _DYNAMIC_MODULES:
                        self.add(node.lineno, "call")

    def _number_ok(self, v, node, parents) -> bool:
        """Whether numeric value v at node is structural IN ITS CONTEXT."""
        p = parents.get(id(node))
        while isinstance(p, ast.Tuple) and isinstance(parents.get(id(p)), ast.Compare):
            p = parents.get(id(p))          # `x in (0, 1)` is judged as the comparison
        if isinstance(p, ast.Compare):
            if v in STRUCTURAL["compare_any"]:
                return True
            return v in STRUCTURAL["compare_eq"] and all(isinstance(o, _EQ_OPS + (ast.In, ast.NotIn))
                                                         for o in p.ops)
        if isinstance(p, ast.BinOp):
            if v in STRUCTURAL["wrap"] and isinstance(p.op, (ast.Mod, ast.Sub, ast.Add, ast.BitAnd)):
                return True
            return (type(p.op), v) in STRUCTURAL["binop"]
        if isinstance(p, ast.AugAssign):
            return v in STRUCTURAL["augassign"] and isinstance(p.op, (ast.Add, ast.Sub))
        if isinstance(p, ast.keyword) or (isinstance(p, ast.Call) and node in p.args):
            return v in STRUCTURAL["call"]
        return v in STRUCTURAL["plain"]

    def _compare(self, node, parents=None):
        operands = [node.left] + list(node.comparators)
        for i, op in enumerate(node.ops):
            pair = (operands[i], operands[i + 1])
            # `v is True` / `v is False` is the three-valued identity test
            # (unknown stays unknown); every other comparison with a boolean
            # constant is a toggle and is refused.
            for x in pair:
                if isinstance(x, ast.Constant) and isinstance(x.value, bool) \
                        and not isinstance(op, (ast.Is, ast.IsNot)):
                    self.add(node.lineno, "bool")
            if not isinstance(op, _SEL_OPS):
                continue
            strings = []
            for x in pair:
                if isinstance(x, ast.Constant) and isinstance(x.value, str):
                    strings.append(x.value)
                elif parents is not None and isinstance(self.resolve(x, parents), str):
                    strings.append(self.resolve(x, parents))         # a followed binding
                elif isinstance(op, (ast.In, ast.NotIn)) and x is pair[1] \
                        and isinstance(x, (ast.Tuple, ast.List, ast.Set)):
                    strings.extend(e.value for e in x.elts
                                   if isinstance(e, ast.Constant) and isinstance(e.value, str))
            if any(s not in SELECTORS for s in strings):
                self.add(node.lineno, "select")

    def _module_bool(self, top):
        nodes = self.tree.body if top is self.tree else [top]
        for n in nodes:
            if isinstance(n, (ast.Assign, ast.AnnAssign)) and isinstance(n.value, ast.Constant) \
                    and isinstance(n.value.value, bool) and n in self.tree.body:
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                if not all(isinstance(t, ast.Name) and (self.mod, t.id) in PINNED for t in targets):
                    self.add(n.lineno, "bool")

    def _fn_of(self, node):
        line = getattr(node, "lineno", 0)
        for name, d in self.defs.items():
            if d.lineno <= line <= getattr(d, "end_lineno", d.lineno):
                return name
        return None

    def _const_arg(self, a):
        return isinstance(a, ast.Constant) and isinstance(a.value, (str, bytes))

    def _call(self, node):
        f = node.func
        name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
        if isinstance(f, ast.Name) and name in _DYNAMIC_CALLS:
            self.add(node.lineno, "call")
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
                and f.value.id in _DYNAMIC_MODULES:
            self.add(node.lineno, "call")
        if name in _DECODERS and node.args and self._const_arg(node.args[0]):
            self.add(node.lineno, "call")
        if name in _DECODERS and node.args and isinstance(node.args[0], (ast.List, ast.Tuple)) \
                and name == "len":
            self.add(node.lineno, "call")
        if name == "setting" and len(node.args) >= 2:
            k = node.args[1]
            key = k.value if isinstance(k, ast.Constant) else self.str_consts.get(getattr(k, "id", ""))
            if key not in SWITCHES:
                self.add(node.lineno, "setting")
        if name in ("getenv",) or (name == "get" and isinstance(f, ast.Attribute)
                                   and isinstance(f.value, ast.Attribute)
                                   and f.value.attr == "environ"):
            self._env_key(node, node.args[0] if node.args else None)

    def _env_subscript(self, node):
        if isinstance(node.value, ast.Attribute) and node.value.attr == "environ":
            self._env_key(node, node.slice)

    def _env_key(self, node, k):
        key = None
        if isinstance(k, ast.Constant):
            key = k.value
        elif isinstance(k, ast.Name):
            key = self.str_consts.get(k.id)
        if key not in ENV_KEYS:
            self.add(node.lineno, "env")

    def check_comments(self, spans=None):
        try:
            toks = tokenize.generate_tokens(io.StringIO(self.src).readline)
            for tok in toks:
                if tok.type == tokenize.COMMENT:
                    line = tok.start[0]
                    if spans is not None and not any(a <= line <= b for a, b in spans):
                        continue
                    if text_bad(tok.string):
                        self.add(line, "text")
        except (tokenize.TokenError, SyntaxError):
            self.add(0, "text")

    # -- reach --
    def names_in(self, node):
        out = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Name):
                out.add(n.id)
            elif isinstance(n, ast.arg):
                out.add("arg:" + n.arg)
        return out

    def roots(self, explicit):
        if explicit is not None:
            return {n for n in explicit if n in self.defs}
        out = set()
        for name, d in self.defs.items():
            names = self.names_in(d)
            if names & REVIEW_NAMES or {"arg:" + p for p in REVIEW_PARAMS} & names:
                out.add(name)
        return out

    def reach(self, roots):
        seen, todo = set(), list(roots)
        while todo:
            n = todo.pop()
            if n in seen:
                continue
            seen.add(n)
            node = self.defs.get(n) or self.assigns.get(n)
            if node is None:
                continue
            for m in self.names_in(node):
                if (m in self.defs or m in self.assigns) and m not in seen:
                    todo.append(m)
        return seen

    def local_imports(self, available, nodes=None):
        out = set()
        for node in ast.walk(self.tree) if nodes is None else [x for n in nodes for x in ast.walk(n)]:
            if isinstance(node, ast.Import):
                out.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                out.add(node.module.split(".")[0])
        return {m for m in out if m in available and m not in INFRA}


def scan_tree(read, available, label_prefix):
    """read(modname) -> source text or None; available = local module names."""
    findings = []
    whole = [m for m in JUDGING if m in available]
    done = set()
    queue = list(whole)
    rooted = [m for m in ROOTED if m in available]
    for m in rooted:
        src = read(m)
        s = _Scan(m, "%s %s%s.py" % (label_prefix, API, m), src)
        reached = s.reach(s.roots(ROOTED[m]))
        nodes = [s.defs.get(n) or s.assigns.get(n) for n in sorted(reached)]
        nodes = [n for n in nodes if n is not None]
        s.check_nodes(nodes)
        spans = [(n.lineno, getattr(n, "end_lineno", n.lineno)) for n in nodes]
        s.check_comments(spans)
        # a module-level import the rooted code relies on is followed whole
        queue.extend(s.local_imports(available, nodes) | (s.local_imports(available) & set(JUDGING)))
        findings.extend(s.findings)
    while queue:
        m = queue.pop()
        if m in done or m in ROOTED:
            continue
        done.add(m)
        src = read(m)
        if src is None:
            continue
        s = _Scan(m, "%s %s%s.py" % (label_prefix, API, m), src)
        s.check_nodes(s.tree.body)
        s.check_comments()
        queue.extend(s.local_imports(available))
        findings.extend(s.findings)
    return findings


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True).stdout


def tree_mode(repo):
    base = os.path.join(repo, *API.split("/"))
    available = {f[:-3] for f in os.listdir(base) if f.endswith(".py")}

    def read(m):
        p = os.path.join(base, m + ".py")
        with open(p, encoding="utf-8") as fh:
            return fh.read()
    return scan_tree(read, available, "tree"), 1


def range_mode(repo, base, tip):
    commits = _git(repo, "rev-list", "--reverse", "%s..%s" % (base, tip)).decode().split()
    findings = []
    for c in commits:
        listing = _git(repo, "ls-tree", "--name-only", c, API).decode().splitlines()
        available = {p[len(API):-3] for p in listing if p.endswith(".py") and "/" not in p[len(API):]}

        def read(m, c=c):
            try:
                return _git(repo, "show", "%s:%s%s.py" % (c, API, m)).decode("utf-8")
            except subprocess.CalledProcessError:
                return None
        findings.extend(scan_tree(read, available, c[:12]))
    return findings, len(commits)


def main(argv):
    if len(argv) == 2 and argv[0] == "tree":
        findings, n = tree_mode(argv[1])
    elif len(argv) == 4 and argv[0] == "range":
        findings, n = range_mode(argv[1], argv[2], argv[3])
    else:
        print(__doc__.split("Modes:")[1].split("Output:")[0].rstrip())
        return 2
    for label, line, cls in findings:
        print("%s:%d %s" % (label, line, cls))
    print("review_guard: %d finding(s) in %d tree(s)" % (len(findings), n))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
