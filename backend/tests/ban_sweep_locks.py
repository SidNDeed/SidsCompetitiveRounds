"""Bans part 2a, FIX-2 classes V and VI: the identity key's lock protocol,
judged by TRANSACTION, from the syntax tree of backend/api.

The identity key is pg_advisory_xact_lock(hashtext(steam_id)), shared or
exclusive (identity_order.py). A TAKING CALL is one invocation of a function
whose own body executes that statement (the statement in a loop is one ordered
pass). Three rules, each a list of findings this module computes:

  1. savepoint_taker_failures: no identity key is taken inside the body of a
     `begin_nested()` savepoint, directly or through a callee. A rollback to
     the savepoint releases an advisory lock taken after it (lesson 718), so
     the statements after it would run unlocked.
  2. segments: within one transaction of an entry (a route handler with its
     dependencies, or a block that opens a session of its own), walked path by
     path through the functions it calls, a second taking call after the first
     is a finding unless SEGMENTS lists it with a reason: every identity key of
     a transaction is taken in its first taking call, or a later call asks only
     for keys the transaction already holds (lesson 204: a transaction that
     holds at most one key of a class is never the middle of a wait chain).
  3. slow_steps: between a taking call and the end of its transaction stands no
     await of a step that waits on something other than the database: a thread
     hop (asyncio.to_thread, run_in_executor), a sleep (asyncio.sleep), or a
     read of a request body (request.body/json/form/stream). The HTTP helpers
     of this code are blocking functions run through a thread hop, so the hop
     is what the rule names.
  4. unkeyed_sorts: a loop over sorted(...) without key=identity_lock_key whose
     body reaches a taker locks ids in an order that is not the one order.

A commit or a rollback of the transaction ends it (and its keys); a commit of
a savepoint does not. Both branches of every `if` are walked, a loop body twice,
every handler of a `try` from the body's entry and end.
"""
from __future__ import annotations

import ast
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))

IDENTITY_KEY = re.compile(
    r"pg_advisory_xact_lock(_shared)?\(\s*hashtext\(\s*(:sid|CAST\(\s*:sid\s+AS\s+text\s*\))\s*\)\s*\)", re.I)
ORDER_KEY = "identity_lock_key"
ROUTE_DECORATORS = frozenset({"get", "post", "put", "patch", "delete", "websocket", "api_route"})
SESSION_OPENERS = ("session", "_sm")
SLOW_CALLS = frozenset({"to_thread", "run_in_executor", "sleep"})
# Functions every path of which ends the caller's transaction; the walk's `try`
# reading (a handler may start from the body's entry) cannot see that.
TXN_ENDERS = {
    "_end_transaction": "auto_logs: a rollback, and close() when the rollback raises; either one "
                        "ends the transaction and every transaction-scoped lock with it",
}
BODY_READS = frozenset({"body", "json", "form", "stream"})


def api_sources(api_dir=API) -> dict:
    out = {}
    for fname in sorted(os.listdir(api_dir)):
        if fname.endswith(".py"):
            with open(os.path.join(api_dir, fname), encoding="utf-8") as fh:
                out[fname[:-3]] = fh.read()
    return out


def functions(sources: dict) -> dict:
    """{module: {name: top-level function node}}"""
    out = {}
    for mod, src in sources.items():
        tree = ast.parse(src)
        out[mod] = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return out


def _name_of(call):
    f = call.func
    return f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)


def _sql_text(call) -> str:
    if not call.args:
        return ""
    a = call.args[0]
    if isinstance(a, ast.Call) and _name_of(a) == "text" and a.args:
        a = a.args[0]
    return "".join(c.value for c in ast.walk(a) if isinstance(c, ast.Constant) and isinstance(c.value, str))


def _own_nodes(fn):
    stack = list(fn.body)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield n
        stack.extend(ast.iter_child_nodes(n))


def is_taking_statement(call) -> bool:
    return isinstance(call, ast.Call) and _name_of(call) != "text" and bool(IDENTITY_KEY.search(_sql_text(call)))


def direct_takers(funcs: dict) -> set:
    """(module, name) of every function whose own body takes the identity key."""
    return {(m, n) for m, fs in funcs.items() for n, fn in fs.items()
            if any(is_taking_statement(c) for c in _own_nodes(fn))}


class _Resolver:
    def __init__(self, funcs):
        self.funcs = funcs
        self.where = {}
        for m, fs in funcs.items():
            for n in fs:
                self.where.setdefault(n, []).append(m)

    def resolve(self, mod, call):
        """The (module, name) a call names: a plain name of the caller's module,
        else the one module that defines it; `module.name` when module is one of
        the api modules."""
        f = call.func
        if isinstance(f, ast.Name):
            if f.id in self.funcs.get(mod, {}):
                return (mod, f.id)
            ms = self.where.get(f.id, [])
            return (ms[0], f.id) if len(ms) == 1 else None
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            base = f.value.id.lstrip("_")
            for m in (f.value.id, base):
                if m in self.funcs and f.attr in self.funcs[m]:
                    return (m, f.attr)
            if f.value.id.endswith("_mod") or f.value.id.startswith("_"):
                ms = self.where.get(f.attr, [])
                return (ms[0], f.attr) if len(ms) == 1 and ms[0] != mod else None
        return None


def _is_savepoint_with(st) -> bool:
    return isinstance(st, (ast.With, ast.AsyncWith)) and any(
        isinstance(it.context_expr, ast.Call) and _name_of(it.context_expr) == "begin_nested" for it in st.items)


def _opens_session(item) -> bool:
    c = item.context_expr
    return (isinstance(c, ast.Call) and isinstance(item.optional_vars, ast.Name)
            and any(k in (_name_of(c) or "").lower() for k in SESSION_OPENERS))


def reaches_taker(funcs, res, takers, mod, node, _seen=None) -> list:
    """The takers a node (a statement list or a function) reaches through calls."""
    seen = set() if _seen is None else _seen
    out = []
    nodes = _own_nodes(node) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else (
        x for s in node for x in ast.walk(s))
    for c in nodes:
        if not isinstance(c, ast.Call):
            continue
        if is_taking_statement(c):
            out.append((mod, "<statement>", c.lineno))
            continue
        tgt = res.resolve(mod, c)
        if tgt is None or tgt in seen:
            continue
        seen.add(tgt)
        if tgt in takers:
            out.append(tgt + (c.lineno,))
        else:
            out += reaches_taker(funcs, res, takers, tgt[0], funcs[tgt[0]][tgt[1]], seen)
    return out


def savepoint_taker_failures(funcs) -> list:
    res, takers = _Resolver(funcs), direct_takers(funcs)
    out = []
    for mod, fs in sorted(funcs.items()):
        for name, fn in sorted(fs.items()):
            for st in _own_nodes(fn):
                if _is_savepoint_with(st):
                    hit = reaches_taker(funcs, res, takers, mod, st.body)
                    if hit:
                        out.append(f"{mod}.{name}:{st.lineno}: a savepoint body takes the identity key "
                                   f"({hit[0][0]}.{hit[0][1]}:{hit[0][2]})")
    return out


def unkeyed_sorts(funcs) -> list:
    res, takers = _Resolver(funcs), direct_takers(funcs)
    out = []
    for mod, fs in sorted(funcs.items()):
        for name, fn in sorted(fs.items()):
            sorted_names = {}
            for st in _own_nodes(fn):
                if (isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name)
                        and isinstance(st.value, ast.Call) and _name_of(st.value) == "sorted"):
                    sorted_names[st.targets[0].id] = st.value
            for st in _own_nodes(fn):
                if not isinstance(st, (ast.For, ast.AsyncFor)):
                    continue
                it = st.iter
                if isinstance(it, ast.Name) and it.id in sorted_names:
                    it = sorted_names[it.id]
                if not (isinstance(it, ast.Call) and _name_of(it) == "sorted"):
                    continue
                if any(k.arg == "key" and ORDER_KEY in ast.dump(k.value) for k in it.keywords):
                    continue
                if reaches_taker(funcs, res, takers, mod, st.body):
                    out.append(f"{mod}.{name}:{st.lineno}: a loop over sorted() without {ORDER_KEY} "
                               f"takes the identity key")
    return out


def entries(funcs) -> list:
    """(module, name, [dependency (module, name)]) of every route handler."""
    res = _Resolver(funcs)
    out = []
    for mod, fs in sorted(funcs.items()):
        for name, fn in sorted(fs.items()):
            if not any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                       and d.func.attr in ROUTE_DECORATORS for d in fn.decorator_list):
                continue
            deps = []
            defaults = list(fn.args.defaults) + [d for d in fn.args.kw_defaults if d is not None]
            for d in defaults:
                if isinstance(d, ast.Call) and _name_of(d) == "Depends" and d.args:
                    tgt = res.resolve(mod, ast.Call(func=d.args[0], args=[], keywords=[]))
                    if tgt is not None and tgt[1] != "get_db":
                        deps.append(tgt)
            out.append((mod, name, deps))
    return out


def session_blocks(funcs) -> list:
    """(module, name) of every function that opens a session of its own; each such
    block is a transaction of its own and is walked as an entry."""
    out = []
    for mod, fs in sorted(funcs.items()):
        for name, fn in sorted(fs.items()):
            if any(isinstance(st, (ast.With, ast.AsyncWith)) and any(_opens_session(i) for i in st.items)
                   for st in _own_nodes(fn)):
                out.append((mod, name))
    return out


def _slow(call) -> str | None:
    cn = _name_of(call)
    if cn == "wait" and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) \
            and call.func.value.id == "asyncio":
        return "wait"
    if cn in SLOW_CALLS:
        base = call.func.value if isinstance(call.func, ast.Attribute) else None
        bn = base.id if isinstance(base, ast.Name) else ""
        if cn == "run_in_executor":
            return cn
        if bn == "asyncio" or (base is None and cn == "to_thread"):
            return cn
        return None
    if cn in BODY_READS and isinstance(call.func, ast.Attribute):
        base = call.func.value
        bn = base.id if isinstance(base, ast.Name) else ""
        if bn in ("request", "req", "websocket", "ws"):
            return f"{bn}.{cn}"
    if cn == "read" and isinstance(call.func, ast.Attribute):
        base = call.func.value
        bn = base.id if isinstance(base, ast.Name) else ""
        if bn in ("file", "upload", "uploaded", "f"):
            return f"{bn}.read"
    return None


class KeyWalk:
    """State: (taking calls in the open transaction (0..2), the frames that took,
    savepoint open, this frame took already). Findings: segments (entry, takers),
    savepoints (entry, taker), slow steps (entry, step, takers)."""

    def __init__(self, funcs):
        self.funcs = funcs
        self.res = _Resolver(funcs)
        self.takers = direct_takers(funcs)
        self.memo = {}
        self.segments = {}
        self.slow = {}
        self.sp_takes = {}
        self.entry = None
        self.mods = []
        self.own = [set()]
        self.loops = []

    def _record(self, book, key, where):
        book.setdefault(key, set()).add(where)

    def walk_entry(self, mod, name, deps=()):
        self.entry = f"{mod}.{name}"
        self.memo = {}
        st = {(0, (), False, False)}
        for dm, dn in deps:
            st = self.call((dm, dn), st, (dn,))
        self.call((mod, name), st, (name,))

    def take(self, states, stack, lineno):
        out = set()
        frame = stack[-1]
        for n, tk, sp, ft in states:
            if ft:
                out.add((n, tk, sp, ft))
                continue
            if sp:
                self._record(self.sp_takes, (self.entry, frame), lineno)
            if n >= 1:
                self._record(self.segments, (self.entry, tk + (frame,)), "/".join(stack[-3:]) + f":{lineno}")
            out.add((min(n + 1, 2), (tk + (frame,))[:4], sp, True))
        return out

    def call(self, tgt, states, stack):
        mod, name = tgt
        out = set()
        for st in states:
            inner = (st[0], st[1], st[2], False)
            key = (mod, name, inner)
            if key not in self.memo:
                self.memo[key] = {inner}
                if name not in stack[:-1] and len(stack) <= 12:
                    fn = self.funcs[mod][name]
                    self.own.append(set())
                    self.mods.append(mod)
                    try:
                        nxt, ret, _x = self.block(fn.body, {inner}, stack)
                    finally:
                        self.own.pop()
                        self.mods.pop()
                    self.memo[key] = nxt | ret
            out |= {(o[0], o[1], o[2], st[3]) for o in self.memo[key]}
        return out

    def expr(self, node, states, stack):
        calls = sorted((c for c in ast.walk(node) if isinstance(c, ast.Call)),
                       key=lambda c: (c.lineno, c.col_offset))
        # A coroutine handed to create_task/ensure_future runs in another task,
        # outside this transaction: it is not walked here (waiting for that task
        # is: asyncio.wait is a slow step).
        spawned = {id(a) for c in calls if _name_of(c) in ("create_task", "ensure_future")
                   for a in c.args for a in [a] if isinstance(a, ast.Call)}
        calls = [c for c in calls if id(c) not in spawned]
        for c in calls:
            cn = _name_of(c)
            own = isinstance(c.func, ast.Attribute) and isinstance(c.func.value, ast.Name) \
                and c.func.value.id in self.own[-1]
            if cn in ("commit", "rollback", "close") and isinstance(c.func, ast.Attribute) and not own:
                base = c.func.value
                bn = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                if "savepoint" in bn.lower() or "nested" in bn.lower():
                    continue
                states = {(0, (), sp, False) for _n, _t, sp, _f in states}
            elif is_taking_statement(c):
                states = self.take(states, stack, c.lineno)
            elif cn in TXN_ENDERS and self.res.resolve(self.mods[-1], c) is not None:
                states = {(0, (), sp, False) for _n, _t, sp, _f in states}
            else:
                step = _slow(c)
                if step is not None:
                    for n, tk, _sp, _f in states:
                        if n >= 1:
                            self._record(self.slow, (self.entry, step, tk), f"{stack[-1]}:{c.lineno}")
                tgt = self.res.resolve(self.mods[-1] if self.mods else None, c)
                if tgt is not None:
                    states = self.call(tgt, states, stack + (tgt[1],))
        return states

    def block(self, stmts, states, stack):
        ret, raised = set(), set()
        for st in stmts:
            if not states:
                break
            if isinstance(st, ast.Raise):
                return set(), ret, raised | self.expr(st, states, stack)
            if isinstance(st, ast.Return):
                states = self.expr(st, states, stack) if st.value is not None else states
                return set(), ret | states, raised
            if isinstance(st, (ast.Continue, ast.Break)) and self.loops:
                self.loops[-1][0 if isinstance(st, ast.Continue) else 1].update(states)
                return set(), ret, raised
            if isinstance(st, ast.If):
                states = self.expr(st.test, states, stack)
                a, ra, xa = self.block(st.body, states, stack)
                b, rb, xb = self.block(st.orelse, states, stack)
                states, ret, raised = a | b, ret | ra | rb, raised | xa | xb
            elif isinstance(st, (ast.For, ast.AsyncFor, ast.While)):
                head = st.iter if hasattr(st, "iter") else st.test
                states = self.expr(head, states, stack)
                self.loops.append([set(), set()])
                try:
                    once, r1, x1 = self.block(st.body, states, stack)
                    once |= self.loops[-1][0]
                    twice, r2, x2 = self.block(st.body, once, stack)
                    twice |= self.loops[-1][0]
                finally:
                    brk = self.loops.pop()[1]
                e, r3, x3 = self.block(st.orelse, states | once | twice, stack)
                states, ret, raised = e | brk, ret | r1 | r2 | r3, raised | x1 | x2 | x3
            elif isinstance(st, (ast.With, ast.AsyncWith)):
                if _is_savepoint_with(st):
                    inner = {(n, tk, True, ft) for n, tk, _sp, ft in states}
                    b, r, x = self.block(st.body, inner, stack)
                    # leaving the savepoint: the outer flag comes back
                    outer_sp = {s[2] for s in states}
                    sp0 = next(iter(outer_sp)) if len(outer_sp) == 1 else False
                    fix = lambda S: {(n, tk, sp0, ft) for n, tk, _sp, ft in S}  # noqa: E731
                    states, ret, raised = fix(b) | fix(x), ret | fix(r), raised | fix(x)
                    continue
                opened = [it for it in st.items if _opens_session(it)]
                for it in st.items:
                    states = self.expr(it.context_expr, states, stack)
                if opened:
                    # a session of the block's own: another transaction, walked from empty
                    for it in opened:
                        self.own[-1].add(it.optional_vars.id)
                    saved = states
                    b, r, x = self.block(st.body, {(0, (), False, False)}, stack)
                    states = saved
                    ret |= {s for s in saved} if r else set()
                    continue
                states, r, x = self.block(st.body, states, stack)
                ret, raised = ret | r, raised | x
            elif isinstance(st, ast.Try) or type(st).__name__ == "TryStar":
                body, r, x = self.block(st.body, states, stack)
                ret, raised = ret | r, raised | x
                h_in = states | body | x
                after, caught = set(), set()
                for h in st.handlers:
                    hs, rh, xh = self.block(h.body, h_in, stack)
                    after |= hs
                    ret, caught = ret | rh, caught | xh
                el, re_, xe = self.block(st.orelse, body, stack)
                after |= el
                ret, raised = ret | re_, raised | xe | caught
                if st.finalbody:
                    fin, rf, xf = self.block(st.finalbody, after | ret, stack)
                    after, ret, raised = fin, ret | rf, raised | xf
                states = after
            elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            else:
                states = self.expr(st, states, stack)
        return states, ret, raised


def walk_all(funcs) -> KeyWalk:
    w = KeyWalk(funcs)
    seen = set()
    for mod, name, deps in entries(funcs):
        w.mods = [mod]
        w.walk_entry(mod, name, deps)
        seen.add((mod, name))
    for mod, name in session_blocks(funcs):
        if (mod, name) in seen:
            continue
        w.mods = [mod]
        w.walk_entry(mod, name)
    return w


def segment_report(w) -> dict:
    """{takers tuple: sorted entries} -- each distinct sequence of taking frames
    in one transaction, with the entries that reach it."""
    out = {}
    for (entry, tk), lines in w.segments.items():
        out.setdefault(tk, set()).add(f"{entry}@{min(lines)}")
    return {k: sorted(v) for k, v in out.items()}


def segment_keys(w) -> set:
    """{(entry, takers)}: the segments the census judges."""
    return set(w.segments)


def slow_report(w) -> dict:
    out = {}
    for (entry, step, tk), wheres in w.slow.items():
        for where in wheres:
            out.setdefault((where, step), set()).add((entry, tk))
    return out
