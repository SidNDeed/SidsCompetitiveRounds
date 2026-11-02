"""H3: one durable per-player gate across holds and every formation writer.

The source census is DSN-free and names every authorized admission span.  The
live controls exercise open and claim refusals plus the common gate in both
target orders for all four queue modes.  CF_TEST_PG_DSN/CF_TEST_PG_OPTOUT have
the same meaning as in the other match-hold PostgreSQL suites.
"""

import asyncio
import ast
import collections
import contextlib
import inspect
import os
import sys
import textwrap
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
sys.path.insert(0, API)
sys.path.insert(0, HERE)

import cf_pg  # noqa: E402
import main  # noqa: E402
import test_match_hold_pg as hold_test  # noqa: E402
import closed_walk as _cw  # noqa: E402
import grammar_shapes_gate as _gg  # noqa: E402
import shape_grammar as _sg  # noqa: E402
from closed_walk import Unclassified  # noqa: E402
# The match_hold the hold suite loaded: the MATCH_HOLD_SRC copy when set
# (a plain import here would bind the tracked copy main cached).
match_hold = hold_test.match_hold


ACQUIRERS = ("_lease_acquire", "_lease_acquire_many")
GATE = "_lease_admission_gate"
Site = collections.namedtuple("Site", "lineno end_lineno callee held")
_INVENTORY = {}


def admission_sites():
    """Every admission call in main.py by the module-level function that makes
    it, in source order: a call of _lease_acquire, _lease_acquire_many or the
    gate itself.  `held` marks an acquire made with _gate_held=True, the form
    a direct gate caller uses after its own gate.  Derived from the AST, not
    listed by hand: a site a reviewer forgot is a site this inventory shows
    and the census below refuses (the re-land's Codex round, F2, found four
    hand-listed omissions: queue_ready's two sites and both continuations)."""
    if "sites" not in _INVENTORY:
        tree = ast.parse(inspect.getsource(main))
        sites = {}
        for fn in tree.body:
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            found = []
            b = _cw.Bindings(main, fn)
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call) and b.named(
                        node.func, ACQUIRERS + (GATE,)) is not None):
                    held = any(kw.arg == "_gate_held" and isinstance(kw.value, ast.Constant)
                               and kw.value.value is True for kw in node.keywords)
                    found.append(Site(node.lineno, node.end_lineno, node.func.id, held))
            if found:
                sites[fn.name] = sorted(found)
        _INVENTORY["sites"], _INVENTORY["tree"] = sites, tree
    return _INVENTORY["sites"]


def formation_sites():
    """(function, k) of every formation site: an unheld acquirer call outside
    the acquirers, k its source-order index among the function's calls."""
    return sorted((name, k) for name, sites in admission_sites().items()
                  if name not in ACQUIRERS
                  for k, site in enumerate(sites, 1)
                  if site.callee in ACQUIRERS and not site.held)


# The census: every function of main.py that makes an admission call, with
# its calls in source order. The two acquirers gate once, and _lease_acquire_many
# then acquires per player under the gate it holds; _rdm_claim gates directly
# and acquires under that gate. Every other entry is a formation site, whose
# refusal takes the shared form checked below. queue_poll, queue_ready and
# team_queue_poll carry two sites each: the polls' room issuance (first in
# source) and their discovery or assembly, in different requests; queue_ready's
# formation renewal and its in-game fence, in one request.
CENSUS = {
    "_lease_acquire": [(GATE, False)],
    "_lease_acquire_many": [(GATE, False), ("_lease_acquire", True)],
    "queue_poll": [("_lease_acquire_many", False)] * 2,
    "queue_ready": [("_lease_acquire_many", False)] * 2,
    "team_queue_poll": [("_lease_acquire_many", False)] * 2,
    "_team_relock_existing_series": [("_lease_acquire_many", False)],
    "team_series_continuation": [("_lease_acquire_many", False)],
    "ovt_queue_poll": [("_lease_acquire_many", False)],
    "ovt_series_continuation": [("_lease_acquire_many", False)],
    "_lobby_enroll_caller": [("_lease_acquire", False)],
    "team_lobby_start": [("_lease_acquire_many", False)],
    "ovt_lobby_start": [("_lease_acquire_many", False)],
    "_ffa_lobby_enroll_caller": [("_lease_acquire", False)],
    "_ffa_lock_roster": [("_lease_acquire_many", False)],
    "_rdm_claim": [(GATE, False), ("_lease_acquire", True)],
    "_ffa_queue_poll_inner": [("_lease_acquire_many", False)],
}


def _statement_of(fn, node):
    """The statement of `fn` that holds `node`."""
    parents = {c: p for p in ast.walk(fn) for c in ast.iter_child_nodes(p)}
    while not isinstance(node, ast.stmt):
        node = parents[node]
    return node


def _next_statement(fn, stmt):
    """The statement right after `stmt` in the statement list that holds it,
    or None."""
    for parent in ast.walk(fn):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(parent, field, None)
            if isinstance(block, list):
                for i, st in enumerate(block):
                    if st is stmt:
                        return block[i + 1] if i + 1 < len(block) else None
    return None


def _is_db_rollback(stmt, b):
    """Whether `stmt` is the statement `await db.rollback()`, `db` read
    through `b` (the walked function's Bindings) as its own parameter bound
    once (ruling REHEARSAL-FOUR-R5, fix 1)."""
    call = (stmt.value.value if isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Await) else None)
    return (isinstance(call, ast.Call) and not call.args and not call.keywords
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "rollback"
            and b.spelled_once(call.func.value, "db", ("param",)))


# --- the closed walks (rehearsal-four rounds 2 and 3, rulings REHEARSAL-FOUR-R2
# and REHEARSAL-FOUR-R3) -------------------------------------------------------
#
# Every walk below is default-deny.  The statements of each walked span take
# one of the named statement shapes listed with its walk (a refusal branch's
# form, the hold refusal, the claim's prefix, a helper's refusing paths);
# anything else fails, naming its construct and its line.  Every expression
# in those statements, and every helper body they await, is classified by
# closed_walk's one shared visitor (ruling REHEARSAL-FOUR-R3): its NODE_TABLE
# names every concrete ast class, a call is classified by its callee shape and
# by every argument kind, and SQL is read from migration_table_ddl's lexer
# tokens.  No other walker reads a span, and nothing falls back to one.  The
# lists below are positive: an entry is here because a real span of main.py or
# match_hold.py, or the design, needs it.  SHAPES_MET counts the statement
# shapes a walk met, per walked function, and each policy's `met` counts the
# visitor's, so the allow-lists are checked by count against the real spans.

SHAPES_MET = collections.Counter()

# Plain calls with no database effect, by callee spelling (text() builds the
# statement an execute runs).
_PLAIN_CALLS = frozenset({"bool", "int", "str", "list", "text", "HTTPException"})
# Methods with no database effect, by attribute name (the result accessors of
# an executed statement, a mapping read, and seat_of, the assembly context's
# in-memory seat lookup).
_PLAIN_METHODS = frozenset({"get", "seat_of", "mappings", "first", "scalar", "append",
                            "update", "log"})
# Awaited library calls with no database effect.
_PLAIN_AWAITS = frozenset()
# The spellings of the walked spans' session.
_SESSIONS = ("db", "ctx.db")
# The one exception a refusal raises.
_REFUSAL_EXCEPTIONS = frozenset({"HTTPException"})
# SQL, read from the lexer's tokens by closed_walk.sql_kind: a read names
# only the functions on the read list (CAST, what the real reads name); a
# write names only those; any other word before a parenthesis, a keyword
# included, is refused until a real statement needs it.  Two entries no real
# span names, kept for the controls' own programs: now() (round 2's F6
# UPDATE, so it is read as the write it is) and the VALUES row constructor
# (round 1's planted INSERT); every other entry is met by the real spans,
# by count.
_SQL_LISTS = _cw.SqlLists(read=frozenset({"cast", "coalesce", "max", "cardinality",
                                         "jsonb_build_object", "unnest",
                                         "clock_timestamp", "now"}),
                          setting=frozenset(),
                          write=frozenset(), syntax=frozenset({"array", "values"}))
# A hold refusal may instead answer the request id another transaction
# already recorded, from that record alone (match_hold._open_replay: "Acts
# on nothing and writes nothing"): a replay on this list, whose own walk by
# the shared visitor shows no write and no commit.
_HOLD_REPLAYS = frozenset({"_open_replay"})
_GATE_POLICIES = {}


# --- the default-deny grammar (rehearsal-four round 7, ruling
# REHEARSAL-FOUR-R6 (1)(b)) ---------------------------------------------------
#
# Before any walk below reasons about a span, grammar_shapes_gate checks it
# against its frozen literals: a site span (the statement holding an
# admission call and its refusal branch; the claim prefix up to its target)
# node by node, with the statements enclosing it by their ancestor shape;
# every function body a walk descends into, whole (closed_walk's helper
# bodies, read through _body while a walk runs; the refusal answers; the hold
# replay); and the binding rule over each whole function. A refusal is the
# walk's answer: `grammar <file>:<line>: <shape>` or `binding <file>:<line>:
# <what>`. _G["record"] is the one-time generator's collector (no test sets
# it); _G["trace"], while set, lists every span and body checked.

_G = {"record": None, "trace": None, "hooks": 0}
_ORIG_HELPER_TREE = _cw._helper_tree
_MAIN_AT = (inspect.getsourcefile(main), 0)


def _source_at(fn):
    """(file, line offset) of function object fn's source."""
    return (inspect.getsourcefile(fn) or inspect.getmodule(fn).__file__,
            fn.__code__.co_firstlineno - 1)


def _body(fn, role):
    """fn's definition, checked whole (grammar_shapes_gate.check_body)
    before any walk reads it."""
    d = _ORIG_HELPER_TREE(fn)
    filename, offset = _source_at(fn)
    n = _gg.check_body(d, role, filename, offset, _G["record"])
    if _G["trace"] is not None:
        _G["trace"].append((role, (fn.__module__, fn.__qualname__), [d], n,
                            None, d))
    return d


def _check_site(fn, stmts, at):
    """Site span `stmts` of fn (grammar_shapes_gate.check_site); `at` is
    (file, line offset) of fn's source."""
    n = _gg.check_site(fn, stmts, at[0], at[1], _G["record"])
    if _G["trace"] is not None:
        _G["trace"].append(("site", (at[0], fn.name), list(stmts), n,
                            _gg.path_to(fn, stmts[0]), fn))


def _helper_tree_checked(fn):
    return _body(fn, "helper")


@contextlib.contextmanager
def _grammar_walk():
    """While a walk runs, every body closed_walk descends into is read
    through _body: closed_walk._helper_tree, its one reader of a function's
    source, is wrapped, and restored when the outermost walk ends."""
    _G["hooks"] += 1
    _cw._helper_tree = _helper_tree_checked
    try:
        yield
    finally:
        _G["hooks"] -= 1
        if not _G["hooks"]:
            _cw._helper_tree = _ORIG_HELPER_TREE


def _gate_policy(scope):
    """The gate walks' policy over `scope` (a module): one per scope, kept
    with the scope so its helper caches and counters persist."""
    key = id(scope)
    if key not in _GATE_POLICIES:
        p = _cw.Policy(scope, _PLAIN_CALLS, _PLAIN_METHODS, _PLAIN_AWAITS,
                       _SQL_LISTS, session=_SESSIONS)
        p.gate_kinds = {}
        p.helper_hook = lambda fn, p=p: _helper_kind(fn, p)
        _GATE_POLICIES[key] = (scope, p)
    return _GATE_POLICIES[key][1]


def _is_docstring(st):
    return (isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant)
            and isinstance(st.value.value, str))


def _awaited_name_call(node, b, name=None):
    """The call of `await <name>(...)` (any plain name when `name` is None),
    `name` read through `b` as the module's."""
    call = node.value if isinstance(node, ast.Await) else None
    if (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            and (name is None or b.named(call.func, (name,)) is not None)):
        return call
    return None


class _Walk:
    """One closed walk over a span of module `scope`: its problems and the
    shapes it met (seen; also counted in SHAPES_MET under `where`)."""

    def __init__(self, scope, where, fn=None, stmts=None):
        self.scope = main if scope is None else scope
        self.policy = _gate_policy(self.scope)
        # The walked function's one resolver (closed_walk.Bindings, ruling
        # REHEARSAL-FOUR-R5 fix 1): every name the walk reads is resolved
        # there, exactly one binding per name or refused; a callee the
        # function binds is never the module's (finding closed_walk:699).
        self.b = _cw.Bindings(self.scope, fn,
                              stmts=[] if fn is None and stmts is None
                              else stmts, session=self.policy.session)
        self.where = where
        self.problems, self.seen = [], []

    def shape(self, name):
        SHAPES_MET[(self.where, name)] += 1

    def fail(self, node, what):
        self.fail_at(getattr(node, "lineno", "?"), what)

    def fail_at(self, line, what):
        self.problems.append(f"line {line}: {what}")


def _resolve(w, func):
    """The function `func` names, resolved by the walk's Bindings (None when
    the walked function binds that name itself; a name bound more than once
    is a problem)."""
    try:
        return w.b.callee(func)
    except Unclassified as e:
        w.fail_at(e.args[0][0] or getattr(func, "lineno", "?"), e.args[0][1])
        return None


def _plain_args(w, call, what):
    """Every argument of `call`, of every kind, is a plain value: no await,
    nothing the shared visitor does not classify, nothing unpacked. A
    session value (`db`, `ctx`) is an argument only where it binds the
    resolved callee's parameter of the same name (Bindings.session_argument,
    ruling REHEARSAL-FOUR-R5 fix 1)."""
    for kind, arg in _cw.call_arguments(call):
        if kind in ("star", "double-star"):
            w.fail(call, f"unpacked arguments in {what}")
            continue
        if w.b.session_value(arg):
            line = getattr(arg, "lineno", 0)
            try:
                w.b.session_root_ok(arg, line)
                w.b.session_argument(call, arg, w.b.callee(call.func), line)
            except Unclassified as e:
                w.fail_at(e.args[0][0] or line, f"{e.args[0][1]} (in {what})")
            continue
        _effects(w, arg, plain_only=True, what=what)


def _effects(w, node, plain_only=False, what="an expression"):
    """The effects of expression `node`, classified by the shared visitor: a
    list of ("read"|"lock"|"write", line, why), ("ends", line, ".commit()" or
    ".rollback()") and ("helper", kind, name, line, why), kind from
    _helper_kind.  A construct the visitor does not classify is a problem
    naming it; with plain_only, so is any await."""
    s = w.policy.session
    ends = frozenset(id(n) for n in ast.walk(node) if isinstance(n, ast.Await)
                     and (_cw.is_db_call(n.value, "commit", s)
                          or _cw.is_db_call(n.value, "rollback", s)))
    v = _cw.Visitor(w.policy, permitted=ends, bindings=w.b)
    try:
        accepted = v.accept(node)
    except Unclassified as e:
        line, msg = e.args[0]
        w.fail_at(line or getattr(node, "lineno", "?"), f"{msg} (in {what})")
        return []
    if plain_only and any(isinstance(n, ast.Await) for n in ast.walk(node)):
        w.fail(node, f"an await inside {what}")
        return []
    # A plain value touches no session: an un-awaited session call (an ORM
    # add, an expire) is a session effect too (finding gate:245).
    if plain_only and any(shape != "call" for shape, _e in accepted.effects):
        w.fail(node, f"a session effect inside {what}")
        return []
    line = getattr(node, "lineno", "?")
    out = []
    for shape, eff in accepted.effects:
        if shape == "sql":
            w.shape(f"execute {eff}")
            out.append((eff, line, eff))
        elif shape.startswith("end:"):
            w.shape(f"await .{shape[4:]}()")
            out.append(("ends", line, f".{shape[4:]}()"))
        elif shape.startswith("helper:"):
            kind, why = eff
            w.shape(f"await helper ({kind})")
            out.append(("helper", kind, shape[7:], line, why))
    return out


_EXITS = object()          # a block every path of which exits
_KEEPS = ("read", "lock", "write", "await")


def _helper_kind(fn, p):
    """(kind, why) of a helper awaited inside a walked span.  Its whole body
    is read by the shared visitor (closed_walk.helper_effects), which refuses
    any construct off its table, any transaction end, and any helper it
    reaches that does either; then:
      "pure"     it awaits nothing a database sees;
      "reads"    its effects are reads (a row lock included);
      "refuses"  it writes, and every write lies on a path that ends in
                 `return await _rdm_refuse(<plain values>)` while every
                 other exit is write-free (its refusing paths, read by
                 _helper_block);
      "writes"   it writes otherwise: a write, allowed only on a refusing
                 path of the span;
      None       anything else, with why: the visitor's refusal, an
                 exception handler that rolls back, a savepoint, or a
                 callback parameter."""
    key = (fn.__module__, fn.__qualname__)
    if key in p.gate_kinds:
        return p.gate_kinds[key]
    p.gate_kinds[key] = (None, f"{fn.__name__} awaits itself")
    try:
        result = _helper_kind_read(fn, p)
    except _gg.Refusal:
        del p.gate_kinds[key]
        raise
    p.gate_kinds[key] = result
    return result


def _helper_kind_read(fn, p):
    try:
        eff = _cw.helper_effects(fn, p)
    except Unclassified as e:
        result = (None, f"{fn.__name__}: {e.args[0][1]}")
    else:
        other = sorted(e for e in eff if e not in _KEEPS)
        if other:
            result = (None, f"{fn.__name__}: {', '.join(other)}, which a span "
                            "that keeps its transaction does not take")
        elif "write" not in eff:
            result = ("reads" if eff & {"read", "lock"} else "pure"), None
        else:
            scope = inspect.getmodule(fn)
            d = _body(fn, "helper")
            w = _Walk(scope, fn.__name__, fn=d)
            state = {"refusals": 0}
            wrote = _helper_block(w, d.body, None, state, top=True)
            if wrote is not _EXITS and wrote is not None:
                w.fail_at("end", f"the implicit return None is a non-refusing "
                                 f"exit after a write (line {wrote})")
            if w.problems or not state["refusals"]:
                result = ("writes", f"{fn.__name__}: "
                          + (w.problems[0] if w.problems else "no refusing path"))
            else:
                result = ("refuses", None)
    return result


def _helper_state(w, node, effects, wrote, state):
    for e in effects:
        if e[0] in ("read", "lock"):
            continue
        elif e[0] == "write":
            wrote = wrote or e[1]
        elif e[0] == "ends":
            w.fail(node, "ends the transaction " + e[2])
        elif e[1] in ("pure", "reads"):
            continue
        elif e[1] in ("writes", "refuses"):
            wrote = wrote or e[3]
        else:
            w.fail(node, f"an awaited call of {e[2]} this walk does not "
                         f"classify ({e[1]}: {e[4]})")
    return wrote


def _is_refusal_exit(st, b):
    """The call of `return await _rdm_refuse(...)`, or None."""
    return (_awaited_name_call(st.value, b, "_rdm_refuse")
            if isinstance(st, ast.Return) else None)


def _refusal_exit_problem(w, st, call):
    """The designed refusal: plain arguments of every kind, and _rdm_refuse
    itself read by the shared visitor, keeping the transaction."""
    _plain_args(w, call, "the refusal's arguments")
    fn = _resolve(w, call.func)
    if fn is None or not inspect.iscoroutinefunction(fn):
        why = "a helper this walk cannot find"
    else:
        try:
            eff = _cw.helper_effects(fn, w.policy)
            other = sorted(e for e in eff if e not in _KEEPS)
            why = f"it takes {', '.join(other)}" if other else None
        except Unclassified as e:
            why = e.args[0][1]
    if why is not None:
        w.fail(st, f"the refusal helper _rdm_refuse is not classified ({why})")


def _helper_block(w, stmts, wrote, state, top=False):
    """Walk a helper's block for its refusing paths; returns the first
    write's line falling out of it (None for none), or _EXITS when every
    path exits."""
    for i, st in enumerate(stmts):
        if top and i == 0 and _is_docstring(st):
            w.shape("docstring")
            continue
        if isinstance(st, ast.Return):
            refusal = _is_refusal_exit(st, w.b)
            if refusal is not None:
                w.shape("exit: return await _rdm_refuse(...)")
                _refusal_exit_problem(w, st, refusal)
                state["refusals"] += 1
            else:
                w.shape("exit: plain return")
                effects = _effects(w, st.value) if st.value is not None else []
                after = _helper_state(w, st, effects, wrote, state)
                if after is not None:
                    w.fail(st, f"a non-refusing exit after a write (line {after})")
            for rest in stmts[i + 1:]:
                w.fail(rest, f"{type(rest).__name__} after an exit")
            return _EXITS
        if isinstance(st, ast.If):
            w.shape("if, walked into")
            wrote = _helper_state(w, st, _effects(w, st.test), wrote, state)
            outs = [x for x in (_helper_block(w, st.body, wrote, state),
                                _helper_block(w, st.orelse, wrote, state))
                    if x is not _EXITS]
            if not outs:
                for rest in stmts[i + 1:]:
                    w.fail(rest, f"{type(rest).__name__} after an exit")
                return _EXITS
            wrote = next((x for x in outs if x is not None), None)
            continue
        if (isinstance(st, ast.Assign) and len(st.targets) == 1
                and isinstance(st.targets[0], ast.Name)):
            w.shape("assign to a local")
            wrote = _helper_state(w, st, _effects(w, st.value), wrote, state)
            continue
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Await):
            w.shape("awaited statement")
            wrote = _helper_state(w, st, _effects(w, st.value), wrote, state)
            continue
        w.fail(st, f"{type(st).__name__} is not a statement shape this walk "
                   f"classifies: {ast.unparse(st)[:50]!r}")
    return wrote


def _hold_block(w, stmts):
    """The hold refusal after its rollback: the refusal's own fresh
    transaction.  Shapes: an awaited call of a named helper with plain
    arguments (as a statement or assigned to a local), an if walked into,
    and exits: a return of a verified refusal (_hold_refusal_problem), or a
    raise of HTTPException with plain arguments.  The helpers' own bodies
    are the fresh transaction's writes and its commit (match_hold.
    _commit_fresh), which the design allows after the rollback; their
    arguments and the if tests are read by the shared visitor.  Round 8: no
    session method is whitelisted here; a commit by one is refused by the
    grammar (grammar_shapes_gate.NARROWED, finding gate:136)."""
    for i, st in enumerate(stmts):
        value = getattr(st, "value", None)
        named = _awaited_name_call(value, w.b)
        if isinstance(st, ast.Expr) and named is not None:
            w.shape("hold: awaited helper call")
            _plain_args(w, named, f"the arguments of {named.func.id}")
        elif (isinstance(st, ast.Assign) and len(st.targets) == 1
              and isinstance(st.targets[0], ast.Name) and named is not None):
            w.shape("hold: assign a helper's answer to a local")
            _plain_args(w, named, f"the arguments of {named.func.id}")
        elif isinstance(st, ast.If):
            w.shape("hold: if, walked into")
            for e in _effects(w, st.test, what="the hold refusal's test"):
                if e[0] != "helper":
                    w.fail(st, f"the hold refusal's test {e[0]}s")
            _hold_block(w, st.body)
            _hold_block(w, st.orelse)
        elif isinstance(st, ast.Return):
            w.shape("hold: exit, return a verified refusal")
            _hold_refusal_problem(w, st)
        elif isinstance(st, ast.Raise):
            w.shape("hold: exit, raise")
            _raise_problem(w, st)
        else:
            w.fail(st, f"{type(st).__name__} is not a statement shape this walk "
                       f"classifies: {ast.unparse(st)[:50]!r}")
            continue
        if isinstance(st, (ast.Return, ast.Raise)):
            for rest in stmts[i + 1:]:
                w.fail(rest, f"{type(rest).__name__} after an exit")
            return


def _hold_refusal_problem(w, st):
    """A hold refusal's return (rehearsal-four round 3, finding gate:578):
    `return <refuser>(<plain values>)`, awaited exactly when <refuser> is a
    coroutine function, where <refuser> is a function of the walked module
    whose every path returns a refusal (_refusal_answer_problem) for the
    reason the call binds."""
    value = st.value
    awaited = isinstance(value, ast.Await)
    call = value.value if awaited else value
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
        w.fail(st, "the hold refusal's return is not a call of a named refusal")
        return
    _plain_args(w, call, "the refusal's arguments")
    name = ast.unparse(call.func)
    fn = _resolve(w, call.func)
    if fn is None:
        w.fail(st, f"the hold refusal {name} is not a function this walk finds")
        return
    if inspect.iscoroutinefunction(fn) != awaited:
        w.fail(st, f"the hold refusal {name} is awaited "
                   f"{'but is not' if awaited else 'not, but is'} a coroutine")
        return
    if w.b.named(call.func, _HOLD_REPLAYS) is not None:
        w.shape("hold: exit, return the replay of the request's own record")
        why = _hold_replay_problem(w, fn)
        if why is not None:
            w.fail(st, f"the hold replay {name} is not classified ({why})")
        return
    why = _refusal_answer_problem(fn, call, (), w.b)
    if why is not None:
        w.fail(st, f"the hold refusal {name} does not answer a refusal: {why}")


def _hold_replay_problem(w, fn):
    """None when replay `fn`, read by the shared visitor with its rollbacks
    permitted, reads (a row lock included) and rolls back only: no write,
    no commit, no savepoint, no callback; else why."""
    try:
        with _grammar_walk():
            eff = _cw.def_effects(_body(fn, "answer"), inspect.getmodule(fn),
                                  w.policy, fn.__name__, rollbacks=True)
    except Unclassified as e:
        return e.args[0][1]
    except _gg.Refusal as e:
        return e.args[0]
    other = sorted(e for e in eff if e not in ("read", "lock", "await", "rollback"))
    return f"it takes {', '.join(other)}" if other else None


def _refusal_answer_problem(fn, call, seen, b):
    """None when `call` (in the function whose Bindings is `b`) binds `fn`'s
    parameter `reason` positionally, with nothing unpacked and no keyword,
    and `fn`'s body is a refusal answer walked whole; else why not.

    Ruling REHEARSAL-FOUR-R5, finding gate:537 (the returns were read and
    the rest of the body was not, so a session call, an attribute store, a
    with, an early raise or an arbitrary await before the answer passed):
    `fn` binds `reason` once, as its parameter, and its body is a closed
    statement shape, every path ending in a return (_answer_block): a
    docstring; an if, its test a plain value read by the shared visitor;
    the statements of the refusal's own fresh transaction, as _hold_block
    reads them (an awaited call of a function of its module with plain
    arguments, a session among them only as that function's same-named
    parameter; round 8: no session method, the commit included, is taken
    here); and a return of either the literal
    `{"status": "refused", "reason": reason, ...}`, its other values plain,
    or the answer of such a refusal of its own module called with `reason`
    (awaited exactly when that refusal is a coroutine function), read the
    same way."""
    if fn in seen:
        return f"{fn.__name__} answers through itself"
    params = list(inspect.signature(fn).parameters)
    if "reason" not in params:
        return f"{fn.__name__} has no reason parameter"
    at = params.index("reason")
    if (call.keywords or any(isinstance(a, ast.Starred) for a in call.args)
            or len(call.args) != len(params) or len(call.args) <= at):
        return f"the call of {fn.__name__} does not bind each parameter once"
    try:
        if seen and not b.spelled_once(call.args[at], "reason", ("param",)):
            return f"{fn.__name__} is not called with its caller's reason"
    except Unclassified as e:
        return f"{fn.__name__} is not called with its caller's reason ({e.args[0][1]})"
    d = _body(fn, "answer")
    w = _Walk(inspect.getmodule(fn), f"refusal answer {fn.__name__}", fn=d)
    try:
        why = _answer_block(w, d.body, seen + (fn,), top=True)
    except Unclassified as e:
        why = f"line {e.args[0][0]}: {e.args[0][1]}"
    if why is None and w.problems:
        why = w.problems[0]
    return None if why is None else f"{fn.__name__} {why}"


def _answer_block(w, stmts, seen, top=False):
    """Why block `stmts` of a refusal answer is not the closed shape
    _refusal_answer_problem names, or None: every path through it ends in
    its answer's return, and nothing follows an exit."""
    for i, st in enumerate(stmts):
        if top and i == 0 and _is_docstring(st):
            continue
        if isinstance(st, ast.If):
            _effects(w, st.test, plain_only=True, what="a refusal answer's test")
            why = _answer_block(w, st.body, seen)
            if why is None and st.orelse:
                why = _answer_block(w, st.orelse, seen)
                if why is None and i + 1 < len(stmts):
                    return f"line {stmts[i + 1].lineno}: a statement after an exit"
            if why is not None:
                return why
            continue
        if isinstance(st, ast.Return):
            why = _answer_return(w, st, seen)
            if why is None and i + 1 < len(stmts):
                return f"line {stmts[i + 1].lineno}: a statement after an exit"
            return why
        value = getattr(st, "value", None)
        call = value.value if isinstance(value, ast.Await) else None
        if isinstance(st, ast.Expr) and isinstance(call, ast.Call):
            fn = (_resolve(w, call.func) if isinstance(call.func, ast.Name)
                  else None)
            if fn is None or not inspect.iscoroutinefunction(fn):
                return (f"line {st.lineno}: an await of "
                        f"{ast.unparse(call.func)}, not a function of its "
                        "module this walk finds")
            _plain_args(w, call, f"the arguments of {ast.unparse(call.func)}")
            continue
        kind = type(st).__name__
        return (f"line {st.lineno}: {'an' if kind[0] in 'AEIOU' else 'a'} "
                f"{kind} in a refusal answer, not a statement shape it takes")
    return (f"can fall off its end (line {stmts[-1].lineno if stmts else '?'})")


def _answer_return(w, st, seen):
    """Why return `st` is not a refusal answer's return, or None."""
    v = st.value
    if isinstance(v, ast.Dict):
        if not all(isinstance(k, ast.Constant) for k in v.keys):
            return f"line {st.lineno} returns another answer"
        got = dict(zip((k.value for k in v.keys), v.values))
        if (len(got) != len(v.keys)
                or not isinstance(got.get("status"), ast.Constant)
                or got["status"].value != "refused"
                or "reason" not in got
                or not w.b.spelled_once(got["reason"], "reason", ("param",))):
            return f"line {st.lineno} returns another answer"
        for k, x in got.items():
            if k not in ("status", "reason"):
                _effects(w, x, plain_only=True, what="a refusal answer's value")
        return w.problems[0] if w.problems else None
    inner = v.value if isinstance(v, ast.Await) else v
    g = (_resolve(w, inner.func) if isinstance(inner, ast.Call)
         and isinstance(inner.func, ast.Name) else None)
    if g is None or inspect.iscoroutinefunction(g) != isinstance(v, ast.Await):
        return f"line {st.lineno} returns another answer"
    _plain_args(w, inner, f"the arguments of {inner.func.id}")
    if w.problems:
        return w.problems[0]
    return _refusal_answer_problem(g, inner, seen, w.b)


def _raise_problem(w, st):
    """A refusal's raise: `raise HTTPException(<plain values>)`, no cause."""
    exc = st.exc
    if not (isinstance(exc, ast.Call) and st.cause is None
            and w.b.named(exc.func, _REFUSAL_EXCEPTIONS) is not None):
        w.fail(st, "the raise is not `raise HTTPException(<plain values>)`")
        return
    _plain_args(w, exc, "the raised refusal")


def _reason_argument(call, b):
    """The argument `call` binds to its callee's `reason` parameter: the
    callee a function of `scope` named by a plain name, called with every
    argument positional, nothing unpacked, no keyword, `reason` among the
    bound and every unbound parameter defaulted; else None (finding gate:535: the last argument was read instead). The callee is resolved by `b`,
    the walked function's Bindings."""
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
        return None
    fn = b.callee(call.func)
    if fn is None:
        return None
    sig = inspect.signature(fn).parameters
    params = list(sig)
    if ("reason" not in params or call.keywords
            or any(isinstance(a, ast.Starred) for a in call.args)
            or any(p.kind not in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                   for p in sig.values())
            or len(call.args) > len(params)
            or params.index("reason") >= len(call.args)
            or any(sig[p].default is sig[p].empty
                   for p in params[len(call.args):])):
        return None
    return call.args[params.index("reason")]


def _is_other_mode(call, b):
    """Whether `call` binds its callee's `reason` to the literal
    "other_mode"."""
    arg = _reason_argument(call, b)
    return isinstance(arg, ast.Constant) and arg.value == "other_mode"


def _returns_other_mode(stmt, b):
    """Whether `stmt` is `return <refusal>(...)`, awaited or not, whose
    `reason` is "other_mode"."""
    value = stmt.value if isinstance(stmt, ast.Return) else None
    if isinstance(value, ast.Await):
        value = value.value
    return _is_other_mode(value, b)


def refusal_branch_violation(fn, call, form, scope=None, at=("<site>", 0)):
    """_refusal_branch_read, a resolver refusal answered as the reason
    (ruling REHEARSAL-FOUR-R5, fix 1), a grammar refusal likewise (round 7);
    `at` is (file, line offset) of fn's source."""
    try:
        with _grammar_walk():
            return _refusal_branch_read(fn, call, form, scope, at)
    except Unclassified as e:
        return f"line {e.args[0][0]}: {e.args[0][1]}"
    except _gg.Refusal as e:
        return e.args[0]


def _refusal_branch_read(fn, call, form, scope=None, at=("<site>", 0)):
    """None when the admission call `call` in function `fn` is answered by its
    own refusal branch in the shape `form` requires, else why not. The branch
    itself is read, never the text after the call: a later rollback in the
    same function answers nothing for this call (rehearsal-four round 1,
    finding 7, where a refusal that commits passed because the loop's
    exhausted-attempts rollback sat in the same tail).  Closed (round 2): the
    admission call's arguments are plain values, and every statement of the
    branch is one of the shapes its form names, every exit with the effects
    inside its own expression.

      shared    the formation sites: `if (await <acquirer>(...)) is False:`,
                whose body is exactly `await db.rollback()` then `raise
                HTTPException(<plain values>)` -- the loser rolls back its
                whole transaction (H3) before it answers, and nothing lies
                between (the design names no statement there);
      direct    _rdm_claim: `admitted, _ = await _lease_admission_gate(...)`
                followed at once by `if not admitted:`, whose body is exactly
                `return await _rdm_refuse(<plain values>, "other_mode")`,
                _rdm_refuse (resolved in `scope`, main by default) read
                by the shared visitor and keeping the transaction;
      acquirer  the two acquirers: the same gate form, refused by exactly
                `return False` (the caller rolls back);
      hold      match_hold open and claim: the same gate form, refused at
                once by `await db.rollback()`, and the branch ends by
                returning its "other_mode" refusal, so it never falls
                through into the action; what lies between is the
                refusal's own fresh transaction (the timeouts rearmed,
                the audit row written), walked by _hold_block.

    Round 7: before anything above is read, the grammar checks the span:
    the statement holding the call and, for the gate forms, the statement
    after it (its refusal branch), each whole, and the statements enclosing
    them by their ancestor shapes (a try, a with or a loop around a refusal
    is refused there: finding gate:769), then the binding rule over fn."""
    stmt = _statement_of(fn, call)
    nxt = _next_statement(fn, stmt) if form != "shared" else None
    _check_site(fn, [stmt] + ([nxt] if nxt is not None else []), at)
    w = _Walk(scope, f"{fn.name} [{form}]", fn=fn)
    # The admission call is the module's (finding gate:1155: a function
    # that rebinds the gate's name passed as the gate).
    if w.b.named(call.func, ACQUIRERS + (GATE,)) is None:
        return "the admission call is not a call of the module's gate or acquirers"
    _plain_args(w, call, f"the arguments of {call.func.id}")
    if w.problems:
        return w.problems[0]
    if form == "shared":
        test = getattr(stmt, "test", None)
        if not (isinstance(stmt, ast.If) and isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Await) and test.left.value is call
                and len(test.ops) == 1 and isinstance(test.ops[0], ast.Is)
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value is False):
            return "the acquisition is not tested `is False` by its own if"
        body = stmt.body
        if not _is_db_rollback(body[0], w.b):
            return "the refusal branch does not open with await db.rollback()"
        if len(body) < 2 or not isinstance(body[-1], ast.Raise):
            return "the refusal branch does not end in a raise"
        w.shape("shared: await db.rollback()")
        for st in body[1:-1]:
            if any(isinstance(n, ast.Await)
                   or (isinstance(n, ast.Attribute) and n.attr in ("commit", "rollback"))
                   for n in ast.walk(st)):
                return (f"line {st.lineno}: the refusal branch awaits or ends a "
                        "transaction after its rollback")
            if isinstance(st, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                return (f"line {st.lineno}: an exit ({type(st).__name__}) before "
                        "the branch's final raise")
            return (f"line {st.lineno}: {type(st).__name__} between the rollback "
                    "and the final raise is not a shape this walk classifies")
        w.shape("shared: exit, raise")
        _raise_problem(w, body[-1])
        return w.problems[0] if w.problems else None
    target = (stmt.targets[0] if isinstance(stmt, ast.Assign)
              and len(stmt.targets) == 1 else None)
    value = getattr(stmt, "value", None)
    # Finding gate:722: the gate answers (admitted, detail); `admitted,
    # admitted = ...` is refused by the binding rule (round 7: admitted is
    # bound at most once in a site), before this walk.
    if not (isinstance(value, ast.Await) and value.value is call
            and isinstance(target, ast.Tuple) and len(target.elts) == 2
            and all(isinstance(e, ast.Name) for e in target.elts)):
        return "the gate's answer is not unpacked into a name and its time"
    flag = ast.unparse(target.elts[0])
    branch = _next_statement(fn, stmt)
    test = getattr(branch, "test", None)
    if not (isinstance(branch, ast.If) and isinstance(test, ast.UnaryOp)
            and isinstance(test.op, ast.Not)
            and w.b.same(test.operand, target.elts[0], ("local",))):
        return f"the gate's answer is not refused at once by `if not {flag}:`"
    first = branch.body[0]
    if form == "hold":
        if not _is_db_rollback(first, w.b):
            return "the refusal branch does not open with await db.rollback()"
        if not _returns_other_mode(branch.body[-1], w.b):
            return ('the refusal branch does not end by returning its '
                    '"other_mode" refusal')
        w.shape("hold: await db.rollback()")
        _hold_block(w, branch.body[1:])
        return w.problems[0] if w.problems else None
    if form == "acquirer":
        if not (isinstance(first, ast.Return)
                and isinstance(first.value, ast.Constant)
                and first.value.value is False):
            return "the refusal branch does not open with return False"
        w.shape("acquirer: exit, return False")
        return _after_exit(branch)
    refused = _is_refusal_exit(first, w.b)
    if refused is not None:
        # its arguments read first, so an unpacked one is named as such
        _refusal_exit_problem(w, first, refused)
        if w.problems:
            return w.problems[0]
    if not (refused is not None and _is_other_mode(refused, w.b)):
        return ('the refusal branch does not open with '
                'return await _rdm_refuse(..., "other_mode")')
    w.shape("direct: exit, return await _rdm_refuse(...)")
    return _after_exit(branch)


def _after_exit(branch):
    """Why the refusal branch holds a statement after its one exit, or None."""
    for rest in branch.body[1:]:
        return (f"line {rest.lineno}: {type(rest).__name__} after the refusal "
                "branch's exit")
    return None


def test_h3_every_admission_site_uses_shared_gate_recheck_and_rollback():
    gate = inspect.getsource(main._lease_admission_gate)
    assert "for pid in pid_text:" in gate
    assert "FOR NO KEY UPDATE" in gate
    assert "queue_leases" in gate and "match_seat_holds" in gate
    assert "ranked_queue" in gate and "team_queue" in gate
    assert "ovt_queue" in gate and "ffa_queue" in gate
    assert "clock_timestamp()" in gate

    found = admission_sites()
    assert {name: [(s.callee, s.held) for s in sites] for name, sites in found.items()} \
        == CENSUS, ("H3 census", found)
    functions = {fn.name: fn for fn in _INVENTORY["tree"].body
                 if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for name, sites in found.items():
        for k, site in enumerate(sites):
            if site.held:
                # An acquire under a gate the function holds: the gate is an
                # earlier call of the same function.
                assert any(s.callee == GATE for s in sites[:k]), (name, site)
                continue
            # Every other call is answered by its own refusal branch, read in
            # that branch (rehearsal-four round 1, finding 7).
            call = next(node for node in ast.walk(functions[name])
                        if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == site.callee
                        and node.lineno == site.lineno)
            form = ("shared" if site.callee != GATE
                    else "acquirer" if name in ACQUIRERS else "direct")
            why = refusal_branch_violation(functions[name], call, form, main,
                                           _MAIN_AT)
            assert why is None, (name, site, form, why)

    open_source = inspect.getsource(match_hold.match_hold_open)
    claim_source = inspect.getsource(match_hold.match_hold_claim)
    for name, source, obj in (("open", open_source, match_hold.match_hold_open),
                              ("claim", claim_source, match_hold.match_hold_claim)):
        fn = ast.parse(textwrap.dedent(source)).body[0]
        calls = [node for node in ast.walk(fn)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                 and node.func.id == "_lease_admission_gate"]
        assert [c.func.id for c in calls] == ["_lease_admission_gate"], (name, calls)
        # The loser rolls back its whole transaction first (H3), in the
        # branch that refuses, not somewhere in the function.
        why = refusal_branch_violation(fn, calls[0], "hold", match_hold,
                                       _source_at(obj))
        assert why is None, (name, why)
    assert "admitted, now = await _lease_admission_gate" in open_source
    assert "admitted, now = await _lease_admission_gate" in claim_source
    assert "_gate_held=True" in claim_source
    for helper in (main._lease_acquire, main._lease_acquire_many):
        source = inspect.getsource(helper)
        calls = [node.func.id for node in ast.walk(
            ast.parse(textwrap.dedent(source)))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "_lease_admission_gate"]
        assert calls == ["_lease_admission_gate"], helper.__name__


_SYNTH = [0]


def _scope_of_lines(lines, consts=None):
    """A module made of `lines` (registered with linecache, so the shared
    visitor reads its functions' source like any module's), with the
    module strings `consts`, and match_hold's two refusals _refused and
    _refuse_attempt bound unless `lines` define their own."""
    import linecache
    import types
    _SYNTH[0] += 1
    name = f"gate_synthetic_{_SYNTH[0]}"
    src = chr(10).join(lines) + chr(10)
    mod = types.ModuleType(name)
    mod.__file__ = f"<{name}>"
    linecache.cache[mod.__file__] = (len(src), None, src.splitlines(True),
                                     mod.__file__)
    sys.modules[name] = mod
    mod._refused = match_hold._refused
    mod._refuse_attempt = match_hold._refuse_attempt
    mod.__dict__.update(consts or {})
    exec(compile(src, mod.__file__, "exec"), mod.__dict__)
    return mod


# --- the direct form's precondition (rehearsal-four round 1, item D) ---------
#
# _rdm_claim's gate refusal does not roll back, and the design says why, in
# the comment above its gate: "under the caller's players row lock, after the
# lobby and queue locks above, it re-reads leases, queue rows and open match
# holds and refuses a commitment outside this lobby. It writes nothing, so the
# refusal row is the only write of a refused claim." So no rollback is needed
# exactly while nothing in the claim's work writes, or ends its transaction,
# before the gate refuses. Locks before the gate are the design's own order,
# not a breach of it, so a locking read is accepted. The work is where the
# readmit route's writes live (_asm_run: "`work` (every write and the answer
# plan)"); the route's lock phase before it may still expire admissions
# (_ffa_expire_admissions), and that expiry commits with any answer, by design.

# Round 8 (finding gate:1140): while "sink" is a list, _calls appends every
# node it reads as (file, line, col, node type), "file" the walked source's.
_INSPECTED = {"sink": None, "file": None}


def _calls(node, stop, b):
    """Whether `node` holds a call of `stop`, the module's (read through
    `b`, the walked function's Bindings: a function that rebinds it is
    refused, finding gate:1155). Every node of `node` is read, none skipped
    after a match, so the prefix walk can compare what it read with what the
    grammar admitted (claim_prefix_violations)."""
    found = False
    for n in ast.walk(node):
        if _INSPECTED["sink"] is not None:
            _INSPECTED["sink"].append(_gg.node_key(_INSPECTED["file"], n))
        if isinstance(n, ast.Call) and b.named(n.func, (stop,)) is not None:
            found = True
    return found


def _prefix_effects(w, st, effects):
    """Classify a prefix statement's effects; returns the name of a refusing
    helper whose answer the statement took, or None."""
    refuser = None
    for e in effects:
        if e[0] in ("read", "lock"):
            w.seen.append((e[0], st.lineno))
        elif e[0] == "write":
            w.fail(st, "writes before the gate")
        elif e[0] == "ends":
            w.fail(st, f"ends the transaction before the gate ({e[2]})")
        elif e[1] in ("pure", "reads", "refuses"):
            w.seen.append((e[1], e[2]))
            if e[1] == "refuses":
                refuser = e[2]
        else:
            w.fail(st, f"an awaited call before the gate this check does not "
                       f"read ({e[2]}: {e[1]}, {e[4]})")
    return refuser


def _prefix_exit(w, st):
    """An exit before the target: `return await _rdm_refuse(<plain values>)`,
    or a return of a plain answer that awaits nothing."""
    refusal = _is_refusal_exit(st, w.b)
    if refusal is not None:
        before = len(w.problems)
        _refusal_exit_problem(w, st, refusal)
        if len(w.problems) == before:
            w.shape("exit: return await _rdm_refuse(...)")
            w.seen.append(("exit", st.lineno))
        return
    if st.value is not None and any(isinstance(n, ast.Await)
                                    for n in ast.walk(st.value)):
        w.fail(st, "an exit before the gate this check does not read")
        return
    before = len(w.problems)
    if st.value is not None:
        _effects(w, st.value, plain_only=True, what="an exit's answer")
    if len(w.problems) == before:
        w.shape("exit: plain return")
        w.seen.append(("exit", st.lineno))


def _prefix_target(w, st, stop):
    """The statement that holds the call of `stop`: an if walked into (its
    test classified, then the statements before the call inside the
    containing branch), or the call as a statement of its own (an
    assignment to names, an expression or a return) with plain arguments."""
    if isinstance(st, ast.If) and not _calls(st.test, stop, w.b):
        w.shape("if around the target, walked into")
        if _prefix_effects(w, st, _effects(w, st.test, what="an if's test")):
            w.fail(st, "the answer of a refusing helper is not refused at once")
        # Round 6, finding gate:1251: every arm that reaches the target is
        # walked (both arms of an if may call it); no arm is chosen over
        # another.
        for arm in (st.body, st.orelse):
            if any(_calls(s, stop, w.b) for s in arm):
                _prefix_block(w, arm, stop)
        return
    if isinstance(st, (ast.Assign, ast.Expr, ast.Return)):
        value = st.value.value if isinstance(st.value, ast.Await) else st.value
        targets = st.targets if isinstance(st, ast.Assign) else []
        names_only = all(isinstance(t, ast.Name) or (
            isinstance(t, ast.Tuple) and all(isinstance(e, ast.Name) for e in t.elts))
            for t in targets)
        if (isinstance(value, ast.Call)
                and w.b.named(value.func, (stop,)) is not None and names_only):
            w.shape(f"target: the call of {stop}")
            _plain_args(w, value, f"the arguments of {stop}")
            return
        w.fail(st, f"the call of {stop} is not a statement of its own")
        return
    w.fail(st, f"{type(st).__name__} around the call of {stop} is not a shape "
               "this walk classifies")


def _prefix_block(w, stmts, stop, top=False):
    """Walk a block of the prefix; True when it reached the call of `stop`."""
    pending = None
    for i, st in enumerate(stmts):
        if _calls(st, stop, w.b):
            if pending is not None:
                w.fail(st, f"the answer of {pending[1]} is not refused at once")
            _prefix_target(w, st, stop)
            # One statement of a block reaches the target; a later one would
            # reach it after a prefix this walk does not read (the "none of
            # them" class, finding gate:1251). Only an if target can be passed
            # without its call, so only then is every later statement read
            # (and admitted by the grammar first: prefix_span, finding
            # gate:1140); a call that is a statement of its own runs on every
            # path through that statement.
            if isinstance(st, ast.If):
                for rest in stmts[i + 1:]:
                    if _calls(rest, stop, w.b):
                        w.fail(rest, f"a second statement reaching {stop}, after "
                                     "a prefix this walk does not read")
            return True
        if top and i == 0 and _is_docstring(st):
            w.shape("docstring")
            continue
        if pending is not None:
            name = pending[0]
            test = getattr(st, "test", None)
            if not (isinstance(st, ast.If) and not st.orelse and len(st.body) == 1
                    and isinstance(test, ast.Compare)
                    and w.b.same(test.left, name, ("local",))
                    and len(test.ops) == 1
                    and isinstance(test.ops[0], ast.IsNot)
                    and isinstance(test.comparators[0], ast.Constant)
                    and test.comparators[0].value is None
                    and isinstance(st.body[0], ast.Return)
                    and w.b.same(st.body[0].value, name, ("local",))):
                w.fail(st, f"the answer of {pending[1]} is not refused at once")
            else:
                w.shape("exit: a refusing helper's answer returned at once")
                w.seen.append(("exit", st.lineno))
            pending = None
            continue
        if isinstance(st, ast.If):
            w.shape("if, walked into")
            if _prefix_effects(w, st, _effects(w, st.test, what="an if's test")):
                w.fail(st, "the answer of a refusing helper is not refused at once")
            _prefix_block(w, st.body, stop)
            _prefix_block(w, st.orelse, stop)
            continue
        if isinstance(st, ast.Return):
            _prefix_exit(w, st)
            continue
        if (isinstance(st, ast.Assign) and len(st.targets) == 1
                and isinstance(st.targets[0], ast.Name)):
            w.shape("assign to a local")
            refuser = _prefix_effects(w, st, _effects(w, st.value))
            if refuser is not None:
                pending = (st.targets[0], refuser)
            continue
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Await):
            w.shape("awaited statement")
            refuser = _prefix_effects(w, st, _effects(w, st.value))
            if refuser is not None:
                w.fail(st, f"the answer of {refuser} is not refused at once")
            continue
        w.fail(st, f"{type(st).__name__} is not a statement shape this walk "
                   f"classifies: {ast.unparse(st)[:50]!r}")
    if pending is not None:
        w.fail(stmts[-1], f"the answer of {pending[1]} is not refused at once")
    return False


def claim_prefix_violations(fn, stop, scope, where="prefix", at=("<site>", 0)):
    """Walk `stmts` from the first statement to the one that calls `stop`,
    closed (round 2): returns (problems, seen).  Every statement on the way is
    one of the named shapes: a docstring; an assignment to a local, or an
    awaited statement, whose expression is plain or awaits a read (SQL on the
    read list, a row lock included) or a helper _helper_kind classifies as
    pure, reads or refuses (a refusing helper's answer refused at once by `if
    <name> is not None: return <name>`); an if walked into, both branches; an
    exit: `return await _rdm_refuse(<plain values>)` or a plain answer that
    awaits nothing.  The statement holding the call is walked into when it is
    an if or a with, so the statements before the call inside its branch are
    classified the same way.  Anything else is refused, naming its line.

    Round 7: `fn` is the function whose body is walked, `at` (file, line
    offset) its source; the grammar checks the span (grammar_shapes_gate.
    prefix_span: the statements up to the first that calls `stop`, and every
    later one when that statement is an if, each whole) and the binding rule
    fn whole, before the walk.

    Round 8 (finding gate:1140): the nodes the grammar admitted and the
    nodes _calls read are both recorded, and any difference between the two
    sets is a problem of the walk (_PREFIX_NODES keeps the last counts)."""
    stmts = fn.body
    admitted, inspected = [], []
    try:
        with _grammar_walk():
            _gg.ADMITTED["sink"] = admitted
            try:
                _check_site(fn, _gg.prefix_span(fn, stop), at)
            finally:
                _gg.ADMITTED["sink"] = None
            w = _Walk(scope, where, stmts=stmts)
            _INSPECTED.update(sink=inspected, file=at[0])
            try:
                if not _prefix_block(w, stmts, stop, top=True):
                    w.problems.append(f"no statement calls {stop}")
            except Unclassified as e:
                w.problems.append(f"line {e.args[0][0]}: {e.args[0][1]}")
            finally:
                _INSPECTED["sink"] = None
    except _gg.Refusal as e:
        return [e.args[0]], []
    w.problems.extend(_node_set_problems(set(inspected), set(admitted)))
    return w.problems, w.seen


_PREFIX_NODES = {"last": None}


def _node_set_problems(inspected, admitted):
    """The M6 assertion: a sentence for each node set difference between
    what the prefix walk read and what the grammar admitted (none when
    equal); the two counts kept in _PREFIX_NODES."""
    _PREFIX_NODES["last"] = (len(inspected), len(admitted))
    out = []
    for what, got in (("inspected but not admitted", inspected - admitted),
                      ("admitted but not inspected", admitted - inspected)):
        if got:
            out.append(f"{len(got)} nodes {what}, the first {min(got, key=str)}")
    return out

_MAIN_DEFS = {}


def _main_def(name):
    """The parsed definition of main's module-level function `name`, or None."""
    if name not in _MAIN_DEFS:
        obj = getattr(main, name, None)
        _MAIN_DEFS[name] = (
            ast.parse(textwrap.dedent(inspect.getsource(obj))).body[0]
            if inspect.isfunction(obj) else None)
    return _MAIN_DEFS[name]


def test_h3_direct_refusal_is_the_claims_first_write():
    """The direct form refuses without a rollback, and that is sound only
    while the refusal row is the claim's first write: nothing from the
    readmit work's entry to _rdm_claim's gate refusal writes or ends the
    transaction (rehearsal-four round 1, item D; the design line is quoted
    above claim_prefix_violations). Checked per statement by
    claim_prefix_violations, never by text."""
    work, claim = _main_def("_asm_readmit_work"), _main_def("_rdm_claim")
    problems, seen_work = claim_prefix_violations(
        work, "_rdm_claim", main, "_asm_readmit_work",
        _source_at(main._asm_readmit_work))
    assert problems == [], problems
    problems, seen = claim_prefix_violations(claim, GATE, main, "_rdm_claim",
                                             _source_at(main._rdm_claim))
    assert problems == [], problems
    # Non-vacuity: the walk read the claim's real prefix -- its refusing and
    # reading helpers, a refusal exit, and the queue row it re-locks before
    # the gate (the design's "after the lobby and queue locks above").
    helpers = {s[1]: s[0] for s in seen if s[0] in ("pure", "reads", "refuses")}
    assert helpers.get("_rdm_live_or_lapse") == "refuses", seen
    assert helpers.get("_rdm_row") == "reads", seen
    assert any(s[0] == "lock" for s in seen), seen
    assert any(s[0] == "exit" for s in seen), seen
    assert ("pure", "_asm_readmit_on") in seen_work, seen_work


def test_h3_real_hold_replay_is_read_and_classified():
    """The hold refusal's replay shape is met by the real open path and
    read by the shared visitor: match_hold._open_replay reads and rolls
    back only, and a copy of it that commits is refused (round 8: by the
    grammar's shape, grammar_shapes_gate.NARROWED, before the visitor's
    "ends the transaction")."""
    w = _Walk(match_hold, "replay probe")
    assert _hold_replay_problem(w, match_hold._open_replay) is None
    src = textwrap.dedent(inspect.getsource(match_hold._open_replay))
    assert src.count("    await db.rollback()" + chr(10)) >= 1
    mutated = src.replace("    await db.rollback()" + chr(10),
                          "    await db.commit()" + chr(10), 1)
    scope = _scope_of_lines(mutated.splitlines())
    for name in ("_open_attempt_row", "_open_attempt_matches", "_hold_row",
                 "_ctx_now", "_state_payload", "_HOLD_COLS"):
        setattr(scope, name, getattr(match_hold, name))
    got = _hold_replay_problem(_Walk(scope, "replay probe"), scope._open_replay)
    assert got is not None and got.endswith(
        ":8: Call.func>Attribute(value=Name,attr='commit',ctx=Load)"), got


def test_h3_hold_open_and_claim_reject_another_live_commitment(monkeypatch):
    async def body(env):
        series, game, _ = await hold_test.opened_series(env, "team", held=1)
        held_pid = series.pid(1)
        other_group = uuid.uuid4()
        await env.conn.execute(
            "INSERT INTO queue_leases (player_id, mode, group_id, generation, expires_at) "
            "VALUES ($1, 'ffa', $2, gen_random_uuid(), clock_timestamp() + interval '5 min')",
            held_pid, other_group)

        refused = await hold_test.open_hold(env, series, 1, 0, game)
        assert refused.status_code == 200 and refused.json() == {
            "status": "refused", "reason": "other_mode"}
        assert await env.conn.fetchval(
            "SELECT count(*) FROM match_seat_holds WHERE player_id=$1", held_pid) == 0
        assert await env.conn.fetchval(
            "SELECT group_id FROM queue_leases WHERE player_id=$1", held_pid) == other_group
        # Round 7 (ruling REHEARSAL-FOUR-R6 (2), effects read by a separate
        # connection after the call): the refused open rolled its action back
        # and committed exactly its own refusal row.
        assert [tuple(r) for r in await env.conn.fetch(
            "SELECT outcome, reason, hold_id FROM match_hold_open_attempts"
            " WHERE held_player_id=$1", held_pid)] == [("refused", "other_mode", None)]

        await env.conn.execute("DELETE FROM queue_leases WHERE player_id=$1", held_pid)
        opened = await hold_test.open_hold(env, series, 1, 0, game)
        assert opened.status_code == 200 and opened.json()["status"] == "opened"
        hold_id = uuid.UUID(opened.json()["hold_id"])
        same_mode_other_group = uuid.uuid4()
        await env.conn.execute(
            "INSERT INTO queue_leases (player_id, mode, group_id, generation, expires_at) "
            "VALUES ($1, 'team', $2, gen_random_uuid(), clock_timestamp() + interval '5 min')",
            held_pid, same_mode_other_group)
        claimed = await hold_test.claim(env, series, 1, hold_id)
        assert claimed == {"status": "refused", "reason": "other_mode"}
        row = await env.conn.fetchrow(
            "SELECT claimed_at, verifier FROM match_seat_holds WHERE id=$1", hold_id)
        assert tuple(row) == (None, None)
        assert await env.conn.fetchval(
            "SELECT group_id FROM queue_leases WHERE player_id=$1", held_pid) == same_mode_other_group
        # Round 7: the refused claim's UPDATE did not apply (above), and its
        # one effect is its committed refusal row, the hold's latest attempt.
        attempts = [tuple(r) for r in await env.conn.fetch(
            "SELECT kind, outcome, reason FROM match_hold_attempts WHERE hold_id=$1"
            " ORDER BY attempt_no", hold_id)]
        assert attempts[-1] == ("claim", "refused", "other_mode"), attempts
        assert ("claim", "ok", None) not in attempts, attempts
        # ...and the same claim, once nothing else holds the player, applies
        # its UPDATE (the positive control of the read above).
        await env.conn.execute("DELETE FROM queue_leases WHERE player_id=$1", held_pid)
        claimed = await hold_test.claim(env, series, 1, hold_id)
        assert claimed["status"] == "claimed", claimed
        row = await env.conn.fetchrow(
            "SELECT claimed_at, verifier FROM match_seat_holds WHERE id=$1", hold_id)
        assert row["claimed_at"] is not None and row["verifier"] is not None

    hold_test.run_env(monkeypatch, body, "h3hold")


@pytest.mark.parametrize("mode", ["ranked", "team", "ovt", "ffa"])
@pytest.mark.parametrize("first", [0, 1])
def test_h3_common_gate_serializes_every_mode_in_both_target_orders(mode, first):
    cf_pg.require_live_pg()

    async def inside():
        async with cf_pg.case("h3gate") as (case, sm):
            seats = await hold_test.seed_players(case.conn, 2)
            pids = [row[0] for row in seats]
            groups = [None, None] if mode == "ranked" else [uuid.uuid4(), uuid.uuid4()]
            winner = groups[first]
            loser = groups[1 - first]
            async with sm() as one, sm() as two:
                admitted, _ = await main._lease_admission_gate(one, pids, mode, winner)
                assert admitted
                for pid in sorted(pids, key=str):
                    await main._lease_acquire(
                        one, pid, mode, winner, main.LEASE_TTL_ASSEMBLY,
                        _gate_held=True)

                waiting = asyncio.create_task(
                    main._lease_admission_gate(two, pids, mode, loser))
                await asyncio.sleep(0.05)
                assert not waiting.done(), "overlapping roster did not wait on the player gate"
                # Round 7 (effects read by a separate connection): nothing
                # of the winner's is visible before its commit...
                assert await case.conn.fetchval(
                    "SELECT count(*) FROM queue_leases") == 0
                await one.commit()
                won = [tuple(r) for r in await case.conn.fetch(
                    "SELECT player_id, mode, group_id, generation, expires_at"
                    " FROM queue_leases ORDER BY player_id::text")]
                assert len(won) == 2
                admitted_two, _ = await asyncio.wait_for(waiting, 2)
                assert not admitted_two
                # ...and the loser's refusal formed and changed no row, read
                # while its transaction is still open and after its rollback.
                for _when in ("refused", "rolled back"):
                    assert [tuple(r) for r in await case.conn.fetch(
                        "SELECT player_id, mode, group_id, generation, expires_at"
                        " FROM queue_leases ORDER BY player_id::text")] == won, _when
                    if _when == "refused":
                        await two.rollback()

            rows = await case.conn.fetch(
                "SELECT player_id, mode, group_id FROM queue_leases ORDER BY player_id::text")
            assert len(rows) == 2
            assert all(row["mode"] == mode and row["group_id"] == winner for row in rows)

    asyncio.run(inside())


# --- rehearsal-four round 7 (ruling REHEARSAL-FOUR-R6) ----------------------
#
# Every prior finding against this file is a control: its program PLANTED in
# the real span it names (the real function's source with one edit, and the
# planted helpers it awaits or returns through, in a module holding
# everything the real module holds), walked by the same entry points as the
# real spans, so every node but the planted ones is a real node, and the
# refusal lands on the program. Each is pinned to the refusal it meets: a
# grammar shape (`grammar <file>:<line>: <shape>`), the binding rule
# (`binding <file>:<line>: <what>`), or a walk's exit or branch sentence (and,
# for the SQL-text programs, closed_walk's retained S lexer sentence). The
# unplanted bases are kept (test_r7_planting_bases_are_kept).


def _planted(module, name, edits=(), helpers=(), helper_edits=()):
    """(definition, scope, at) of `module`.`name` with `edits` applied to its
    source (each old text found exactly once), parsed; `scope` a module
    holding everything `module` holds plus `helpers` (source lines) and the
    real helpers named in `helper_edits` with their own edits; `at` the
    planted source's (file, line offset)."""
    import linecache
    import types

    def edited(text, pairs, what):
        for old, new in pairs:
            assert text.count(old) == 1, (what, text.count(old), old)
            text = text.replace(old, new)
        return text

    src = edited(textwrap.dedent(inspect.getsource(getattr(module, name))),
                 edits, name)
    lines = list(helpers)
    for helper, pairs in helper_edits:
        lines += edited(textwrap.dedent(inspect.getsource(getattr(module, helper))),
                        pairs, helper).splitlines()
    _SYNTH[0] += 1
    mod_name = f"gate_planted_{_SYNTH[0]}"
    mod = types.ModuleType(mod_name)
    mod.__dict__.update({k: v for k, v in module.__dict__.items()
                         if not k.startswith("__")})
    # One file name per planted function, so a pinned refusal names it.
    mod.__file__ = f"<planted helpers for {name}>"
    text = chr(10).join(lines) + chr(10)
    linecache.cache[mod.__file__] = (len(text), None, text.splitlines(True),
                                     mod.__file__)
    sys.modules[mod_name] = mod
    exec(compile(text, mod.__file__, "exec"), mod.__dict__)
    return ast.parse(src).body[0], mod, (f"<planted {name}>", 0)


def _wrapped(text, head, tail):
    """`text` (whole lines at four spaces) one level deeper, between `head`
    and `tail` (lines at four spaces)."""
    deeper = chr(10).join(("    " + ln) if ln else ln for ln in text.split(chr(10)))
    return head + chr(10) + deeper + chr(10) + tail


# The real spans the controls plant into: (module, function, entry, target).
SHARED = ("main", "_lobby_enroll_caller", "branch:shared", "_lease_acquire")
DIRECT = ("main", "_rdm_claim", "branch:direct", GATE)
ACQUIRER = ("main", "_lease_acquire", "branch:acquirer", GATE)
HOLD = ("match_hold", "match_hold_claim", "branch:hold", GATE)
PREFIX_WORK = ("main", "_asm_readmit_work", "prefix", "_rdm_claim")
PREFIX_CLAIM = ("main", "_rdm_claim", "prefix", GATE)
R7_BASES = (SHARED, DIRECT, ACQUIRER, HOLD, PREFIX_WORK, PREFIX_CLAIM)

_S_BRANCH = ('''    if (await _lease_acquire(
            db, player.id, cfg["lease"], lobby_id,
            LEASE_TTL_POLLING)) is False:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="You're in a live match in another mode - finish it first")''')
_S_RB = '''        await db.rollback()
        raise HTTPException(
            status_code=409,'''
_D_GATE = '''    admitted, _ = await _lease_admission_gate(ctx.db, [pid], "ffa", ctx.lid)'''
_D_REFUSE = '''    if not admitted:
        return await _rdm_refuse(ctx, pid, me, "claim", n, "other_mode")'''
_A_GATE = '''        admitted, _ = await _lease_admission_gate(
            db, [player_id], mode, group_id,'''
_H_GATE = '''    admitted, now = await _lease_admission_gate(
            db, [pid], hold["mode"], hold["series_id"],'''
_H_BRANCH = '''    admitted, now = await _lease_admission_gate(
            db, [pid], hold["mode"], hold["series_id"],
            allowed_hold_ids=(hold_id,), hold_entry_bound_seconds=ENTRY_BOUND_S,
            strict_team_ovt_queue=True)
    if not admitted:
        # Roll back the losing claim before its required audit row. Re-locking
        # the hold gives the fresh audit transaction its numbering invariant.
        await db.rollback()
        await _install_database_timeouts(db)
        await _guard_hold_identities(db, hold_id, req.steam_id)
        hold = await _hold_row(db, hold_id, lock=True)
        if hold is None:
            raise HTTPException(404, "no such hold")
        now = await _ctx_now(db)
        return await _refuse_attempt(db, hold_id, "claim", now, "other_mode")'''
_H_REFUSE = '''        return await _refuse_attempt(db, hold_id, "claim", now, "other_mode")
    if not _hold_live(hold, now):'''
_W_TARGET = '''    if req.step == "claim":
        return await _rdm_claim(ctx, pid, me, req)'''
_UPDATE = ('await ctx.db.execute(text("UPDATE ffa_seat_readmissions SET claimed_at'
           ' = now()"), {"pid": pid})')
_LAPSE = '''        await _rdm_end_hold(ctx, me, "lapsed", depart=True)
'''
_ROW_DEF = "async def _rdm_row(ctx, pid, n):" + chr(10)


# Finding gate:1140's program (round 7 report): a statement after the claim
# target that reaches _rdm_claim through a computed callee, which _calls reads
# (it is a statement after an if target) and which the round-7 span never
# admitted.
_R8_SUFFIX_LABEL = "a later dispatch branch reaching _rdm_claim through a computed callee"
_R8_SUFFIX = ('    if req.step == "x":' + chr(10)
              + '        return await (lambda: _rdm_claim)()(ctx, pid, me, req)')


def _hold_returns(expr):
    """The hold branch's refusal replaced by `return <expr>`."""
    return [(_H_REFUSE, f"        return {expr}" + chr(10)
             + "    if not _hold_live(hold, now):")]


def _answer(*body, head="def evil(reason: str) -> dict:"):
    """A refusal answer `evil` with `body` before its refusal."""
    return ([head] + ["    " + ln for ln in body]
            + ["    return {\"status\": \"refused\", \"reason\": reason}"])


# (finding, label, real span, edits, helper lines, helper edits, the refusal)
R7_CONTROLS = [
    # round 1
    ("r1 gate:136", "a committing refusal (M1a)", SHARED,
     [(_S_RB, _S_RB.replace("db.rollback()", "db.commit()"))], (), (),
     "grammar <planted _lobby_enroll_caller>:148: Call.func>Attribute(value=Name,attr='commit',ctx=Load)"),
    # round 2
    ("r2 gate:498", "an UPDATE before _rdm_claim in its dispatch branch",
     PREFIX_WORK, [(_W_TARGET, _W_TARGET.replace(
         "        return", "        " + _UPDATE + chr(10) + "        return"))],
     (), (), 'grammar <planted _asm_readmit_work>:9: <root>>If(test=Compare,body=[Expr|Return],orelse=[])'),
    ("r2 gate:498", "a commit before _rdm_claim in its dispatch branch",
     PREFIX_WORK, [(_W_TARGET, _W_TARGET.replace(
         "        return", "        await ctx.db.commit()" + chr(10) + "        return"))],
     (), (), 'grammar <planted _asm_readmit_work>:9: <root>>If(test=Compare,body=[Expr|Return],orelse=[])'),
    ("r2 gate:417", "SQL COMMIT as a statement before the gate",
     PREFIX_CLAIM, [(_D_GATE, '    await ctx.db.execute(text("COMMIT"), {"pid": pid})'
                     + chr(10) + _D_GATE)], (), (),
     'grammar <planted _rdm_claim>:36: <root>>Expr(value=Await)'),
    ("r2 gate:417", "SQL COMMIT as the text of a real read before the gate",
     PREFIX_CLAIM, [('"SELECT mode, group_id FROM queue_leases"', '"COMMIT"')], (), (),
     "a transaction command in SQL text (COMMIT)"),
    ("r2 gate:417", "SQL ROLLBACK as the text of a real read before the gate",
     PREFIX_CLAIM, [('"SELECT mode, group_id FROM queue_leases"', '"ROLLBACK"')], (), (),
     "a transaction command in SQL text (ROLLBACK)"),
    ("r2 gate:417", "SQL ROLLBACK as a statement before the gate",
     PREFIX_CLAIM, [(_D_GATE, '    await ctx.db.execute(text("ROLLBACK"), {"pid": pid})'
                     + chr(10) + _D_GATE)], (), (),
     'grammar <planted _rdm_claim>:36: <root>>Expr(value=Await)'),
    ("r2 gate:456", "return None after _rdm_end_hold in a refusal-only helper",
     PREFIX_CLAIM, [], (),
     [("_rdm_live_or_lapse", [(_LAPSE, _LAPSE + "        return None" + chr(10))])],
     'line 8: an awaited call before the gate this check does not read (_rdm_live_or_lapse: writes, _rdm_live_or_lapse: line 14: a non-refusing exit after a write (line 13))'),
    ("r2 gate:225", "a commit inside _rdm_refuse's arguments", DIRECT,
     [(_D_REFUSE, _D_REFUSE.replace("(ctx, pid,", "(ctx, await ctx.db.commit(),"))],
     (), (), 'grammar <planted _rdm_claim>:38: Await.value>Call(func=Name,args=[Await|Constant|Name],keywords=[])'),
    ("r2 gate:225", "an early successful return before the shared final raise",
     SHARED, [(_S_RB, _S_RB.replace("        raise", "        return {\"status\": "
                                     "\"formed\"}" + chr(10) + "        raise"))],
     (), (), 'grammar <planted _lobby_enroll_caller>:145: <root>>If(test=Compare,body=[Expr|Raise|Return],orelse=[])'),
    # round 3
    ("r3 gate:298", "a computed callee in the refusal's arguments", DIRECT,
     [(_D_REFUSE, _D_REFUSE.replace("(ctx, pid,", "(ctx, [str][0](await ctx.db.commit()),"))],
     (), (), 'grammar <planted _rdm_claim>:38: Await.value>Call(func=Name,args=[Call|Constant|Name],keywords=[])'),
    ("r3 gate:419", "a match statement in a refusing helper", PREFIX_CLAIM, [], (),
     [("_rdm_live_or_lapse", [(_LAPSE, "        match pid:" + chr(10)
                               + "            case _:" + chr(10)
                               + "                pass" + chr(10) + _LAPSE)])],
     'grammar <planted helpers for _rdm_claim>:12: AsyncFunctionDef.body>If(test=Compare,body=[Expr|Match|Return],orelse=[])'),
    ("r3 gate:578", "a hold 'refusal' that answers formed", HOLD,
     _hold_returns('success("other_mode")'),
     ["def success(reason: str) -> dict:", "    return {\"status\": \"formed\"}"], (),
     'grammar <planted helpers for match_hold_claim>:2: Return.value>Dict(keys=[Constant],values=[Constant])'),
    # round 4
    ("r4 gate:647", "a second assignment target on the acquirer's gate", ACQUIRER,
     [(_A_GATE, _A_GATE.replace("admitted, _ =", "admitted, _ = rows[await db.commit()] ="))],
     (), (), 'grammar <planted _lease_acquire>:13: <root>>Assign(targets=[Subscript|Tuple],value=Await,type_comment=-)'),
    ("r4 gate:647", "a second assignment target on the hold claim's gate", HOLD,
     [(_H_GATE, _H_GATE.replace("admitted, now =",
                                "admitted, now = rows[await db.commit()] ="))],
     (), (), 'grammar <planted match_hold_claim>:25: <root>>Assign(targets=[Subscript|Tuple],value=Await,type_comment=-)'),
    ("r4 gate:1080", "a with around the claim target", PREFIX_WORK,
     [(_W_TARGET, '''    if req.step == "claim":
        with ctx as rows[await ctx.db.commit()]:
            return await _rdm_claim(ctx, pid, me, req)''')], (), (), 'grammar <planted _asm_readmit_work>:9: <root>>If(test=Compare,body=[With],orelse=[])'),
    ("r4 gate:535", "other_mode bound to another parameter", HOLD,
     _hold_returns('fake("hold_lapsed", "other_mode")'),
     ["def fake(reason: str, unused) -> dict:",
      "    return {\"status\": \"refused\", \"reason\": reason}"], (), 'the refusal branch does not end by returning its "other_mode" refusal'),
    ("r4 gate:541", "a refusal answer that rebinds reason", HOLD,
     _hold_returns('rebinds("other_mode")'),
     _answer('reason = "not_other_mode"', head="def rebinds(reason: str) -> dict:"),
     (), 'grammar <planted helpers for match_hold_claim>:2: FunctionDef.body>Assign(targets=[Name],value=Constant,type_comment=-)'),
    ("r4 gate:541", "a refusal answer through a match", HOLD,
     _hold_returns('by_match("other_mode")'),
     _answer("match reason:", "    case _:", "        pass",
             head="def by_match(reason: str) -> dict:"), (), 'grammar <planted helpers for match_hold_claim>:1: <root>>FunctionDef(name=str,args=arguments,body=[Match|Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])'),
    ("r4 gate:541", "a refusal answer through a computed lambda call", HOLD,
     _hold_returns('by_lambda("other_mode")'),
     ["def by_lambda(reason: str) -> dict:",
      "    return (lambda r: {\"status\": \"refused\", \"reason\": r})(reason)"], (),
     'grammar <planted helpers for match_hold_claim>:2: Return.value>Call(func=Lambda,args=[Name],keywords=[])'),
    # round 5
    ("r5 gate:537", "a session call in the answer", HOLD,
     _hold_returns('evil("other_mode")'), _answer("db.add(reason)"), (), 'grammar <planted helpers for match_hold_claim>:2: FunctionDef.body>Expr(value=Call)'),
    ("r5 gate:537", "an attribute store in the answer", HOLD,
     _hold_returns('evil("other_mode")'), _answer("db.answer = reason"), (),
     'grammar <planted helpers for match_hold_claim>:2: FunctionDef.body>Assign(targets=[Attribute],value=Name,type_comment=-)'),
    ("r5 gate:537", "a with in the answer", HOLD,
     _hold_returns('evil("other_mode")'), _answer("with db:", "    pass"), (),
     'grammar <planted helpers for match_hold_claim>:1: <root>>FunctionDef(name=str,args=arguments,body=[Return|With],decorator_list=[],returns=Name,type_comment=-,type_params=[])'),
    ("r5 gate:537", "an effect inside the returned answer", HOLD,
     _hold_returns('evil("other_mode")'),
     ["def evil(reason: str) -> dict:",
      "    return {\"status\": \"refused\", \"reason\": reason, \"x\": db.add(reason)}"],
     (), 'grammar <planted helpers for match_hold_claim>:2: Return.value>Dict(keys=[Constant],values=[Call|Constant|Name])'),
    ("r5 gate:537", "an early raise in the answer", HOLD,
     _hold_returns('evil("other_mode")'),
     _answer("if reason:", "    raise RuntimeError(reason)"), (), 'grammar <planted helpers for match_hold_claim>:2: FunctionDef.body>If(test=Name,body=[Raise],orelse=[])'),
    ("r5 gate:537", "an arbitrary await in the answer", HOLD,
     _hold_returns('await evil(db, hold_id, "claim", now, "other_mode")'),
     _answer("await arbitrary(db)", head="async def evil(db, hold_id, kind, now, reason):"),
     (),
     'line 39: the hold refusal evil does not answer a refusal: evil line 2: an await of arbitrary, not a function of its module this walk finds'),
    ("r5 gate:1155", "the gate rebound", DIRECT,
     [(_D_GATE, "    _lease_admission_gate = _rdm_row" + chr(10) + _D_GATE)], (), (),
     'binding <planted _rdm_claim>:36: binds _lease_admission_gate (store)'),
    ("r5 gate:1155", "the claim target rebound", PREFIX_WORK,
     [(_W_TARGET, "    _rdm_claim = _rdm_bind" + chr(10) + _W_TARGET)], (), (),
     'grammar <planted _asm_readmit_work>:9: <root>>Assign(targets=[Name],value=Name,type_comment=-)'),
    ("r5 gate:602", "the raised refusal rebound", SHARED,
     [(_S_BRANCH, "    HTTPException = db.add" + chr(10) + _S_BRANCH)], (), (),
     'binding <planted _lobby_enroll_caller>:145: binds HTTPException (store)'),
    ("r5 gate:722", "the admission flag unpacked twice", DIRECT,
     [(_D_GATE, _D_GATE.replace("admitted, _", "admitted, admitted"))], (), (),
     'binding <planted _rdm_claim>:36: binds admitted (store) 2 times, frozen at most 1'),
    # round 6
    ("r6 gate:578", "a recursive refusal through a *reason parameter", HOLD,
     _hold_returns('evil("other_mode")'),
     ["def evil(reason: str) -> dict:", "    return inner(reason)",
      "def inner(*reason) -> dict:",
      "    return {\"status\": \"refused\", \"reason\": reason}"], (), 'grammar <planted helpers for match_hold_claim>:3: FunctionDef.args>arguments(posonlyargs=[],args=[],vararg=arg,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[])'),
    ("r6 gate:578", "a recursive refusal forwarding *reason", HOLD,
     _hold_returns('evil("other_mode")'),
     ["def evil(reason: str) -> dict:", "    return inner(*reason)",
      "def inner(reason: str) -> dict:",
      "    return {\"status\": \"refused\", \"reason\": reason}"], (), 'grammar <planted helpers for match_hold_claim>:2: Return.value>Call(func=Name,args=[Starred],keywords=[])'),
    ("r6 gate:769", "the shared refusal wrapped in finally: return formed", SHARED,
     [(_S_BRANCH, _wrapped(_S_BRANCH, "    try:",
                           "    finally:" + chr(10) + "        return {\"status\": \"formed\"}"))],
     (), (), 'grammar <planted _lobby_enroll_caller>:145: AsyncFunctionDef.body>Try'),
    ("r6 gate:769", "the hold refusal wrapped in finally: return formed", HOLD,
     [(_H_BRANCH, _wrapped(_H_BRANCH, "    try:",
                           "    finally:" + chr(10) + "        return {\"status\": \"formed\"}"))],
     (), (), 'grammar <planted match_hold_claim>:25: AsyncFunctionDef.body>Try'),
    ("r6 gate:1251", "both arms of an if reach _rdm_claim, an UPDATE in the else",
     PREFIX_WORK, [(_W_TARGET, _W_TARGET + chr(10) + "    else:" + chr(10)
                    + "        " + _UPDATE + chr(10)
                    + "        return await _rdm_claim(ctx, pid, me, req)")],
     (), (), 'grammar <planted _asm_readmit_work>:9: <root>>If(test=Compare,body=[Return],orelse=[Expr|Return])'),
    ("r6 gate:1251", "both arms of a conditional expression reach _rdm_claim",
     PREFIX_WORK, [(_W_TARGET, '''    if req.step == "claim":
        return await (_rdm_claim(ctx, pid, me, req) if pid else _rdm_claim(ctx, pid, me, req))''')],
     (), (), 'grammar <planted _asm_readmit_work>:10: Return.value>Await(value=IfExp)'),
    ("r6 gate:1251", "a second statement reaching _rdm_claim after an UPDATE",
     PREFIX_WORK, [(_W_TARGET, _W_TARGET + chr(10) + "    " + _UPDATE + chr(10)
                    + "    return await _rdm_claim(ctx, pid, me, req)")],
     (), (), 'grammar <planted _asm_readmit_work>:11: <root>>Expr(value=Await)'),
    # round 7 (codex-rehearsal-four-r7.out M6, finding gate:1140): a statement
    # after an if target is read for a second call of the target; round 8
    # admits each such statement first (grammar_shapes_gate.prefix_span), and
    # the walk asserts that the nodes it read are the nodes admitted.
    ("r7 gate:1140", _R8_SUFFIX_LABEL, PREFIX_WORK,
     [(_W_TARGET, _W_TARGET + chr(10) + _R8_SUFFIX)], (), (),
     "grammar <planted _asm_readmit_work>:12: Await.value>Call(func=Call,args=[Name],keywords=[])"),
    ("r7 gate:1140", "an UPDATE in a later dispatch branch, then a computed reach",
     PREFIX_WORK, [(_W_TARGET, _W_TARGET + chr(10) + _R8_SUFFIX.replace(
         "        return", "        " + _UPDATE + chr(10) + "        return"))],
     (), (), "grammar <planted _asm_readmit_work>:11: <root>>If(test=Compare,body=[Expr|Return],orelse=[])"),
    # another child's (the database bound): whether the grammar refuses its shape
    ("r4 gate:245", "a session effect in _rdm_claim's arguments", PREFIX_WORK,
     [(_W_TARGET, _W_TARGET.replace("(ctx, pid,", "(ctx, ctx.db.add(pid),"))],
     (), (), 'grammar <planted _asm_readmit_work>:10: Await.value>Call(func=Name,args=[Call|Name],keywords=[])'),
    # one control per round-7 rule that only that rule refuses (its mutant's)
    ("r7 body", "an assert in a body closed_walk descends into (_rdm_row)",
     PREFIX_CLAIM, [], (),
     [("_rdm_row", [(_ROW_DEF, _ROW_DEF + "    assert pid" + chr(10))])], 'grammar <planted helpers for _rdm_claim>:1: <root>>AsyncFunctionDef(name=str,args=arguments,body=[Assert|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])'),
    ("r7 import", "a local import of the gate that is not a frozen import",
     DIRECT, [(_D_GATE, "    from main import _lease_admission_gate" + chr(10)
               + _D_GATE)], (), (),
     "binding <planted _rdm_claim>:36: an import outside the frozen imports: "
     "('from', 'main', 0, (('_lease_admission_gate', None),))"),
    ("r6 closed_walk:406 form", "the gate imported from another module",
     DIRECT, [(_D_GATE, "    from match_hold import _lease_admission_gate" + chr(10)
               + _D_GATE)], (), (),
     "binding <planted _rdm_claim>:36: an import outside the frozen imports: ('from', 'match_hold', 0, (('_lease_admission_gate', None),))"),
    ("r7 pair", "a meaningful spelling bound in a site that never reads it",
     SHARED, [(_S_BRANCH, "    _rdm_refuse = db" + chr(10) + _S_BRANCH)], (), (),
     'binding <planted _lobby_enroll_caller>:145: binds _rdm_refuse (store)'),
    ("r7 count", "admitted bound twice in a shared site", SHARED,
     [(_S_BRANCH, "    admitted = 1" + chr(10) + "    admitted = 2" + chr(10)
       + _S_BRANCH)], (), (), 'binding <planted _lobby_enroll_caller>:145: binds admitted (store) 2 times, frozen at most 1'),
    ("generic", "SELECT lo_create(0) as the text of a real read (the S lexer rule)",
     PREFIX_CLAIM, [('"SELECT mode, group_id FROM queue_leases"',
                     '"SELECT lo_create(0)"')], (), (), 'line 15: a SQL function off the read allow-list: lo_create (in an expression)'),
    # the round-1 oracle's planted refusals (#391), on the real spans
    ("oracle", "the shared branch does not end in a raise", SHARED,
     [(_S_BRANCH, _S_BRANCH.split(chr(10) + "        raise")[0])], (), (), 'grammar <planted _lobby_enroll_caller>:145: <root>>If(test=Compare,body=[Expr],orelse=[])'),
    ("oracle", "the shared acquisition tested `is not False`", SHARED,
     [(_S_BRANCH, _S_BRANCH.replace(")) is False:", ")) is not False:"))], (), (),
     'grammar <planted _lobby_enroll_caller>:145: If.test>Compare(left=Await,ops=[IsNot],comparators=[Constant])'),
    ("oracle", "a statement between the gate and its refusal", DIRECT,
     [(_D_GATE, _D_GATE + chr(10) + "    n = int(req.n)")], (), (), "the gate's answer is not refused at once by `if not admitted:`"),
    ("oracle", "the acquirer's refusal does not return False", ACQUIRER,
     [("        if not admitted:" + chr(10) + "            return False",
       "        if not admitted:" + chr(10) + "            return True")], (), (),
     'the refusal branch does not open with return False'),
    ("oracle", "the hold refusal answers another reason", HOLD,
     _hold_returns('await _refuse_attempt(db, hold_id, "claim", now, "lobby_closed")'),
     (), (), 'the refusal branch does not end by returning its "other_mode" refusal'),
    ("oracle", "the hold refusal awaits before its rollback", HOLD,
     [("        await db.rollback()" + chr(10) + "        await _install_database_timeouts(db)",
       "        await _install_database_timeouts(db)" + chr(10) + "        await db.rollback()")],
     (), (), 'the refusal branch does not open with await db.rollback()'),
    ("generic", "a lambda call before the gate", PREFIX_CLAIM,
     [(_D_GATE, "    n = (lambda: n)()" + chr(10) + _D_GATE)], (), (), 'grammar <planted _rdm_claim>:36: Assign.value>Call(func=Lambda,args=[],keywords=[])'),
    ("generic", "a walrus before the gate", PREFIX_CLAIM,
     [(_D_GATE, "    if (q := ctx.row) is None:" + chr(10) + "        return q"
       + chr(10) + _D_GATE)], (), (), 'grammar <planted _rdm_claim>:36: If.test>Compare(left=NamedExpr,ops=[Is],comparators=[Constant])'),
    ("generic", "SELECT lo_create(0) before the gate (the S lexer rule)",
     PREFIX_CLAIM, [(_D_GATE, '    await ctx.db.execute(text("SELECT lo_create(0)"), '
                     '{"pid": pid})' + chr(10) + _D_GATE)], (), (), 'grammar <planted _rdm_claim>:36: <root>>Expr(value=Await)'),
]
_R7_MODULES = {"main": main, "match_hold": match_hold}


R7_KEPT = [("kept", f"the real {b[1]} ({b[2]})", b, (), (), (), None)
           for b in R7_BASES]


@pytest.mark.parametrize("row", R7_KEPT + R7_CONTROLS,
                         ids=[f"{r[0]} {r[1]}" for r in R7_KEPT + R7_CONTROLS])
def test_r7_prior_findings_are_refused(row):
    """Ruling REHEARSAL-FOUR-R6 (3): every prior finding against this file is
    refused by the grammar (its shape), the binding rule, or a walk's exit or
    branch sentence, each pinned (R7_CONTROLS' last column); the first
    refusal a walk meets is the one pinned. The kept rows: every real span
    the controls plant into, planted with nothing, is admitted, so a
    control's refusal is its program's, never the harness's."""
    finding, label, base, edits, helpers, helper_edits, want = row
    modname, name, entry, target = base
    fn, scope, at = _planted(_R7_MODULES[modname], name, edits, helpers,
                             helper_edits)
    if entry == "prefix":
        got = claim_prefix_violations(fn, target, scope, name, at)[0]
        got = got[0] if got else None
    else:
        # the planted function's one call of `target`, by its spelling
        call = next(n for n in ast.walk(fn) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Name) and n.func.id == target)
        got = refusal_branch_violation(fn, call, entry.split(":")[1], scope, at)
    if want is None:
        assert got is None, (label, got)
    else:
        assert got is not None and want in got, (finding, label, want, got)


def test_r7_grammar_covers_every_walked_span_and_body():
    """The completeness assertion (ruling REHEARSAL-FOUR-R6 (1)(b)): over the
    real walks (the census, the hold forms, the claim prefix, the replay),
    every function whose source was read during them was checked by the
    grammar, as a site span or a whole body; the nodes checked equal the
    nodes of those spans and bodies, counted again here; and the refusal
    list of every one of them (shape_grammar.refusals, ancestors, the binding
    rule) is empty at this commit."""
    admission_sites()
    _GATE_POLICIES.clear()
    read, real_getsource = [], inspect.getsource

    def spy(obj):
        read.append(obj)
        return real_getsource(obj)

    _G["trace"] = []
    inspect.getsource = spy
    try:
        test_h3_every_admission_site_uses_shared_gate_recheck_and_rollback()
        test_h3_direct_refusal_is_the_claims_first_write()
        assert _hold_replay_problem(_Walk(match_hold, "replay"),
                                    match_hold._open_replay) is None
        trace = _G["trace"]
    finally:
        inspect.getsource = real_getsource
        _G["trace"] = None
        _GATE_POLICIES.clear()
    # Read only for the census's text assertions, never walked:
    text_only = {("main", "_lease_admission_gate")}
    bodies = {key for role, key, *_rest in trace if role != "site"}
    sites = {key[1] for role, key, *_rest in trace if role == "site"}
    for obj in read:
        if inspect.isfunction(obj):
            key = (obj.__module__, obj.__qualname__)
            assert key in bodies or key in text_only or obj.__name__ in sites, key
    checked = recount = 0
    for role, key, trees, n, path, fn in trace:
        checked += n
        recount += (len(path) if path else 0) + sum(len(_sg.visit(t)) for t in trees)
        for node, parent, field in path or ():
            assert _gg.ancestor_shape(node, parent, field) in _gg.ANCESTORS, key
        for t in trees:
            assert _sg.refusals(t, _gg.SHAPES, "<real>") == [], (key, t.lineno)
        assert _gg.binding_problems(
            fn, role, _gg.MEANINGFUL | _gg.callees(trees), "<real>", 0) == [], key
    assert checked == recount, (checked, recount)
    print(f"r7 grammar: {len(trace)} checks, {len(bodies)} bodies, "
          f"{len(sites)} site functions, {checked} nodes checked, "
          f"{len(_gg.SHAPES)} shapes, {len(_gg.ANCESTORS)} ancestor shapes")


def test_r8_prefix_walks_read_exactly_the_nodes_the_grammar_admits(monkeypatch):
    """Finding gate:1140 (round 7 M6): the set of nodes the prefix walk
    reads (_calls, every node of every statement it is given) equals the set
    of nodes the grammar admitted (grammar_shapes_gate.nodes over
    prefix_span), compared as (file, line, col, node type), on both real
    prefix walks and on every prefix control the grammar admits; and a
    control where the two differ (the round-7 span, to the first target
    only, on the report's program) is a problem of the walk."""
    counts = {}
    for name, stop in (("_asm_readmit_work", "_rdm_claim"), ("_rdm_claim", GATE)):
        problems, _ = claim_prefix_violations(
            _main_def(name), stop, main, name, _source_at(getattr(main, name)))
        assert problems == [], (name, problems)
        counts[name] = _PREFIX_NODES["last"]
        assert counts[name][0] == counts[name][1] > 0, counts
    compared = 0
    for row in R7_KEPT + R7_CONTROLS:
        modname, name, entry, target = row[2]
        if entry != "prefix":
            continue
        fn, scope, at = _planted(_R7_MODULES[modname], name, row[3], row[4], row[5])
        _PREFIX_NODES["last"] = None
        got = claim_prefix_violations(fn, target, scope, name, at)[0]
        if _PREFIX_NODES["last"] is None:
            assert got and got[0].startswith("grammar "), (row[1], got)
            continue
        compared += 1
        assert not [p for p in got if " nodes inspected but not admitted" in p
                    or " nodes admitted but not inspected" in p], (row[1], got)
    assert compared >= 4, compared

    def round7_span(fn, stop):
        out = []
        for st in fn.body:
            out.append(st)
            if stop in _gg.callees([st]):
                break
        return out

    row = next(r for r in R7_CONTROLS if r[1] == _R8_SUFFIX_LABEL)
    fn, scope, at = _planted(main, "_asm_readmit_work", row[3])
    monkeypatch.setattr(_gg, "prefix_span", round7_span)
    problems, _ = claim_prefix_violations(fn, "_rdm_claim", scope,
                                          "_asm_readmit_work", at)
    assert problems and all(" nodes inspected but not admitted" in p
                            for p in problems), problems
    print(f"r8 M6 inspected/admitted: {counts}, prefix controls compared {compared}; "
          f"round-7 span on the report's program: {problems[0]}")


def test_r8_refusal_commit_is_the_modules_fresh_commit(monkeypatch):
    """Production conformation (round 8, M3 finding gate:136): the refusal
    audit row's transaction is committed by match_hold._commit_fresh (a
    commit, nothing else), and _refuse_attempt writes its row, commits, and
    answers the refusal, in that order. The live effect (the committed row,
    read by a separate connection) is test_h3_hold_open_and_claim_reject_
    another_live_commitment's."""
    calls = []

    class Db:
        async def commit(self):
            calls.append("commit")

        async def rollback(self):
            calls.append("rollback")

        async def flush(self):
            calls.append("flush")

    async def attempt(db, hold_id, kind, now, outcome, reason=None):
        calls.append(("attempt", hold_id, kind, now, outcome, reason))

    monkeypatch.setattr(match_hold, "_attempt", attempt)
    assert asyncio.run(match_hold._commit_fresh(Db())) is None
    assert calls == ["commit"], calls
    calls.clear()
    got = asyncio.run(match_hold._refuse_attempt(Db(), "h", "claim", "t", "other_mode"))
    assert got == {"status": "refused", "reason": "other_mode"}, got
    assert calls == [("attempt", "h", "claim", "t", "refused", "other_mode"),
                     "commit"], calls


def test_r8_readmit_work_dispatches_every_step(monkeypatch):
    """Production conformation (round 8, M6; patch RF/r8/gg/main-asm-readmit-
    work.patch): _asm_readmit_work's last step reads `if req.step ==
    "entered":` (a root-level return is outside the frozen gate grammar);
    the route admits only _RDM_STEPS, and each of them still reaches its own
    step function with the same arguments and answers its answer."""
    seen = []

    def step(name):
        async def run(ctx, pid, me, req):
            seen.append((name, pid, me, req.step))
            return {"step": name}
        return run

    async def readmit_on(db, lobby):
        return True

    for name in ("_rdm_claim", "_rdm_bind", "_rdm_decline", "_rdm_entered"):
        monkeypatch.setattr(main, name, step(name))
    monkeypatch.setattr(main, "_asm_readmit_on", readmit_on)

    class Ctx:
        db, lobby = object(), {}

        def seat_of(self, pid):
            return ("seat", pid)

    class Req:
        n = 1

    assert main._RDM_STEPS == frozenset({"claim", "bind", "decline", "entered"})
    for st in sorted(main._RDM_STEPS):
        req = Req()
        req.step = st
        seen.clear()
        got = asyncio.run(main._asm_readmit_work(Ctx(), "p", req))
        assert got == {"step": "_rdm_" + st}, (st, got)
        assert seen == [("_rdm_" + st, "p", ("seat", "p"), st)], (st, seen)
