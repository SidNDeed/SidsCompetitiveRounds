"""H3: one durable per-player gate across holds and every formation writer.

The source census is DSN-free and names every authorized admission span.  The
live controls exercise open and claim refusals plus the common gate in both
target orders for all four queue modes.  CF_TEST_PG_DSN/CF_TEST_PG_OPTOUT have
the same meaning as in the other match-hold PostgreSQL suites.
"""

import asyncio
import ast
import collections
import inspect
import os
import re
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
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id in ACQUIRERS + (GATE,)):
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


def _is_db_rollback(stmt):
    """Whether `stmt` is the statement `await db.rollback()`."""
    call = (stmt.value.value if isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Await) else None)
    return (isinstance(call, ast.Call) and not call.args and not call.keywords
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "rollback"
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "db")


# --- the closed walks (rehearsal-four round 2, ruling REHEARSAL-FOUR-R2) -----
#
# Every walk below is default-deny.  Each statement of a walked span, and each
# node of each expression in it, is positively classified into one of the
# named shapes listed here; anything else fails, naming its construct and its
# line.  The lists are positive: an entry is here because a real span of
# main.py or match_hold.py, or the design, needs it.  SHAPES_MET counts the
# shapes a walk met, per walked function, so the allow-list is checked by
# count against the real spans (the round's shapes log).

SHAPES_MET = collections.Counter()

# Expression nodes with no effect of their own.
_PLAIN_NODES = (ast.Constant, ast.Name, ast.Attribute, ast.Subscript, ast.Slice,
                ast.Tuple, ast.List, ast.Dict, ast.BinOp, ast.BoolOp,
                ast.Compare, ast.UnaryOp, ast.IfExp, ast.JoinedStr,
                ast.FormattedValue, ast.ListComp, ast.comprehension, ast.keyword,
                ast.expr_context, ast.operator, ast.boolop, ast.cmpop,
                ast.unaryop)
# Calls with no database effect: builtins by name; methods by attribute name
# (the result accessors of an executed statement, a mapping read, and
# seat_of, the assembly context's in-memory seat lookup).
_PLAIN_BUILTINS = frozenset({"bool", "int", "str", "len", "list", "tuple",
                             "min", "max"})
_PLAIN_METHODS = frozenset({"get", "seat_of", "mappings", "first", "scalar"})
# The one exception a refusal raises.
_REFUSAL_EXCEPTIONS = frozenset({"HTTPException"})
# SQL: a read is one statement whose head is SELECT, that names no DML, and
# whose every function is on this read-only list (a row lock, FOR UPDATE or
# FOR NO KEY UPDATE, is a read the design requires before the gate).  A write
# is one INSERT, UPDATE or DELETE statement.  A transaction command ends the
# transaction.  Anything else is SQL the walk does not read.
_SQL_READ_FUNCTIONS = frozenset({"CAST", "COALESCE", "COUNT", "MAX", "MIN",
                                 "NOW", "CLOCK_TIMESTAMP", "ANY"})
_SQL_PAREN_KEYWORDS = frozenset({"IN", "EXISTS", "FROM", "JOIN", "WHERE", "AND",
                                 "OR", "NOT", "ON", "AS", "SELECT"})
_SQL_WRITE_HEADS = frozenset({"INSERT", "UPDATE", "DELETE"})
_SQL_TXN_HEADS = frozenset({"COMMIT", "ROLLBACK", "SAVEPOINT", "BEGIN", "START",
                            "RELEASE", "END", "ABORT", "PREPARE"})
_SQL_WRITES = re.compile(r"\b(?:INSERT|UPDATE|DELETE|MERGE|TRUNCATE|COPY|INTO)\b", re.I)
_SQL_ROW_LOCK = re.compile(r"\bFOR\s+(?:NO\s+KEY\s+)?UPDATE\b", re.I)


def _sql_clean(sql):
    """`sql` with comments, string literals and quoted names blanked."""
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"'(?:[^']|'')*'", " '' ", sql)
    return re.sub(r'"(?:[^"]|"")*"', ' "" ', sql)


def _sql_shape(sql):
    """(kind, why): kind "read", "lock", "write" or "ends", or None with why."""
    clean = _sql_clean(sql)
    if "$" in re.sub(r"\$\d+", " ", clean) or "'" in clean.replace("''", ""):
        return None, "a dollar quote or an unterminated literal"
    body = clean.strip().rstrip(";").strip()
    if ";" in body:
        return None, "more than one statement"
    if re.search(r'""\s*\(', body):
        return None, "a quoted function name"
    head = (re.match(r"[A-Za-z]+", body) or [""])[0].upper()
    if head in _SQL_TXN_HEADS:
        return "ends", head
    if head in _SQL_WRITE_HEADS:
        return "write", head
    if head != "SELECT":
        return None, f"the statement head {head or body[:12]!r} is not on the list"
    if _SQL_WRITES.search(_SQL_ROW_LOCK.sub(" ", body)):
        return "write", "SELECT naming DML"
    for name in re.findall(r"\b([A-Za-z_][A-Za-z_0-9]*)\s*\(", body):
        if name.upper() not in _SQL_READ_FUNCTIONS | _SQL_PAREN_KEYWORDS:
            return None, f"the function {name} is not on the read-only list"
    return ("lock" if _SQL_ROW_LOCK.search(body) else "read"), head


def _execute_sql(call, consts):
    """The SQL of `<x>.execute(text(<sql>), ...)` when <sql> is a string literal
    or a module-level string named in `consts`; None for any other call."""
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            and call.func.attr == "execute" and call.args):
        return None
    inner = call.args[0]
    if not (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
            and inner.func.id == "text" and len(inner.args) == 1
            and not inner.keywords):
        return None
    arg = inner.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.Name) and isinstance(consts.get(arg.id), str):
        return consts[arg.id]
    return None


def _is_docstring(st):
    return (isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant)
            and isinstance(st.value.value, str))


def _awaited_name_call(node, name=None):
    """The call of `await <name>(...)` (any plain name when `name` is None)."""
    call = node.value if isinstance(node, ast.Await) else None
    if (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            and (name is None or call.func.id == name)):
        return call
    return None


class _Walk:
    """One closed walk: its problems, the shapes it met (seen; also counted in
    SHAPES_MET under `where`), and the helper kinds it classified."""

    def __init__(self, lookup, consts, where, kinds=None):
        self.lookup = lookup or (lambda name: None)
        self.consts = consts or {}
        self.where = where
        self.kinds = {} if kinds is None else kinds
        self.problems, self.seen = [], []

    def shape(self, name):
        SHAPES_MET[(self.where, name)] += 1

    def fail(self, node, what):
        self.problems.append(f"line {getattr(node, 'lineno', '?')}: {what}")


def _plain_args(w, call, what):
    """Every argument of `call` is a plain value: no await, no call off the
    plain lists (the effects inside an exit's own expression)."""
    for arg in list(call.args) + [k.value for k in call.keywords]:
        _effects(w, arg, plain_only=True, what=what)


def _effects(w, node, plain_only=False, what="an expression"):
    """The effects of expression `node`: a list of ("read"|"lock", line),
    ("write"|"ends"|"unread", line, detail) and ("helper", kind, name, line,
    why).  Every node must be plain, a plain call, or (unless plain_only) an
    await of an execute, a commit or rollback, or a named helper; anything else
    is a problem naming its construct."""
    out = []

    def visit(n):
        if isinstance(n, ast.Await):
            if plain_only:
                w.fail(n, f"an await inside {what}")
                return
            out.append(_await_effect(w, n))
            return
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id in _PLAIN_BUILTINS:
                w.shape(f"plain call {f.id}()")
            elif isinstance(f, ast.Attribute) and f.attr in _PLAIN_METHODS:
                w.shape(f"plain method .{f.attr}()")
                visit(f.value)
            elif isinstance(f, (ast.Name, ast.Attribute)):
                w.fail(n, f"a call of {ast.unparse(f)} inside {what} is not a "
                          "shape this walk classifies")
                return
            else:
                visit(f)                    # names the callee's own construct
                return
            for arg in list(n.args) + [k.value for k in n.keywords]:
                visit(arg)
            return
        if not isinstance(n, _PLAIN_NODES):
            w.fail(n, f"{type(n).__name__} inside {what} is not a shape this "
                      "walk classifies")
            return
        for c in ast.iter_child_nodes(n):
            visit(c)

    visit(node)
    return out


def _await_effect(w, node):
    call, line = node.value, node.lineno
    if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute):
        attr = call.func.attr
        if attr in ("commit", "rollback") and not call.args and not call.keywords:
            w.shape(f"await .{attr}()")
            return ("ends", line, f".{attr}()")
        if attr == "execute":
            _effects(w, call.func.value, plain_only=True, what="an execute's target")
            for arg in list(call.args[1:]) + [k.value for k in call.keywords]:
                _effects(w, arg, plain_only=True, what="an execute's parameters")
            sql = _execute_sql(call, w.consts)
            if sql is None:
                return ("unread", line, "an execute whose SQL is not a literal "
                                        "or a module string")
            kind, why = _sql_shape(sql)
            if kind is None:
                return ("unread", line, f"SQL this walk does not read: {why}")
            w.shape(f"execute {kind} ({why})")
            return (kind, line, why)
    named = _awaited_name_call(node)
    if named is not None:
        _plain_args(w, named, f"the arguments of {named.func.id}")
        kind, why = _helper_kind(w.lookup(named.func.id), w.lookup, w.consts,
                                 w.kinds, named.func.id)
        w.shape(f"await helper ({kind})")
        return ("helper", kind, named.func.id, line, why)
    return ("unread", line, f"an await of {ast.unparse(call)[:40]} this walk "
                            "does not classify")


def _txn_free(fn, lookup, consts, visiting=None):
    """None when nothing reachable from `fn` ends its transaction, else why:
    every await reachable through `fn` and the module functions it calls is
    an execute of read or write SQL or an await of such a function; no
    commit or rollback is named; no async with, async for or yield.  The
    property a write on a refusing path needs: it may write, and the refusal
    commits with it."""
    if fn is None:
        return "a helper this walk cannot find"
    visiting = set() if visiting is None else visiting
    if fn.name in visiting:
        return None
    visiting.add(fn.name)
    for n in ast.walk(fn):
        if isinstance(n, (ast.AsyncWith, ast.AsyncFor, ast.Yield, ast.YieldFrom)):
            return f"{fn.name} line {n.lineno}: {type(n).__name__}"
        if isinstance(n, ast.Attribute) and n.attr in ("commit", "rollback"):
            return f"{fn.name} line {n.lineno}: names .{n.attr}"
        if isinstance(n, ast.Await):
            sql = _execute_sql(n.value, consts)
            if sql is not None:
                kind, why = _sql_shape(sql)
                if kind not in ("read", "lock", "write"):
                    return f"{fn.name} line {n.lineno}: SQL {kind or why}"
                continue
            if _awaited_name_call(n) is None:
                return f"{fn.name} line {n.lineno}: an await this walk does not classify"
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id != fn.name):
            sub = lookup(n.func.id)
            if sub is None and _awaited_name_call_target(fn, n):
                return f"{fn.name} line {n.lineno}: awaits {n.func.id}, not found"
            if sub is not None:
                why = _txn_free(sub, lookup, consts, visiting)
                if why is not None:
                    return why
    return None


def _awaited_name_call_target(fn, call):
    """Whether `call` is the operand of an await in `fn`."""
    return any(isinstance(n, ast.Await) and n.value is call for n in ast.walk(fn))


_EXITS = object()          # a block every path of which exits


def _helper_kind(fn, lookup, consts, kinds=None, name=None):
    """(kind, why) of a helper awaited inside a walked span, classified by
    walking its body closed, every exit with the effects before it:
      "pure"     it awaits nothing a database sees;
      "reads"    its awaits are reads, and every exit returns;
      "refuses"  it writes only on paths that end in `return await
                 _rdm_refuse(<plain values>)`, and every other exit is
                 write-free;
      "writes"   any other helper nothing reachable from which ends its
                 transaction (_txn_free): a write, allowed only on a
                 refusing path;
      None       anything else, with why."""
    if fn is None:
        return None, f"{name}: a helper this walk cannot find"
    kinds = {} if kinds is None else kinds
    if fn.name in kinds:
        return kinds[fn.name]
    kinds[fn.name] = (None, f"{fn.name} awaits itself")
    w = _Walk(lookup, consts, fn.name, kinds)
    state = {"refusals": 0, "reads": 0}
    wrote = _helper_block(w, fn.body, None, state, top=True)
    if wrote is not _EXITS and wrote is not None:
        w.fail(fn.body[-1], f"the implicit return None is a non-refusing exit "
                            f"after a write (line {wrote})")
    if w.problems:
        why = f"{fn.name}: {w.problems[0]}"
        free = _txn_free(fn, lookup, consts)
        result = ("writes", why) if free is None else (None, f"{why}; {free}")
    elif state["refusals"]:
        result = ("refuses", None)
    elif state["reads"]:
        result = ("reads", None)
    else:
        result = ("pure", None)
    kinds[fn.name] = result
    return result


def _helper_state(w, node, effects, wrote, state):
    for e in effects:
        if e[0] in ("read", "lock"):
            state["reads"] += 1
        elif e[0] == "write":
            wrote = wrote or e[1]
        elif e[0] in ("ends", "unread"):
            w.fail(node, ("ends the transaction " if e[0] == "ends" else "") + e[2])
        elif e[1] == "reads":
            state["reads"] += 1
        elif e[1] == "writes":
            wrote = wrote or e[3]
        elif e[1] != "pure":
            w.fail(node, f"an awaited call of {e[2]} this walk does not "
                         f"classify ({e[1]}: {e[4]})")
    return wrote


def _is_refusal_exit(st):
    """The call of `return await _rdm_refuse(...)`, or None."""
    return _awaited_name_call(st.value, "_rdm_refuse") if isinstance(st, ast.Return) else None


def _refusal_exit_problem(w, st, call):
    """The designed refusal: plain arguments, and nothing reachable from
    _rdm_refuse ends the transaction."""
    _plain_args(w, call, "the refusal's arguments")
    why = _txn_free(w.lookup("_rdm_refuse"), w.lookup, w.consts)
    if why is not None:
        w.fail(st, f"the refusal helper _rdm_refuse is not classified ({why})")


def _helper_block(w, stmts, wrote, state, top=False):
    """Walk a helper's block; returns the first write's line falling out of
    it (None for none), or _EXITS when every path exits."""
    for i, st in enumerate(stmts):
        if top and i == 0 and _is_docstring(st):
            w.shape("docstring")
            continue
        if isinstance(st, ast.Return):
            refusal = _is_refusal_exit(st)
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
    arguments (as a statement or assigned to a local), the commit of that
    transaction, an if walked into, and exits: a return of a named helper's
    answer (awaited or not) with plain arguments, or a raise of
    HTTPException with plain arguments.  The helpers' own bodies are the
    fresh transaction's writes, which the design allows after the rollback."""
    for i, st in enumerate(stmts):
        value = getattr(st, "value", None)
        named = _awaited_name_call(value)
        if isinstance(st, ast.Expr) and named is not None:
            w.shape("hold: awaited helper call")
            _plain_args(w, named, f"the arguments of {named.func.id}")
        elif (isinstance(st, ast.Expr) and isinstance(value, ast.Await)
              and _await_is_commit(value)):
            w.shape("hold: commit of the refusal's own transaction")
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
        elif isinstance(st, ast.Return) and (
                named is not None or (isinstance(value, ast.Call)
                                      and isinstance(value.func, ast.Name))):
            w.shape("hold: exit, return a helper's answer")
            _plain_args(w, named or value, "the refusal's arguments")
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


def _await_is_commit(node):
    call = node.value
    return (isinstance(call, ast.Call) and not call.args and not call.keywords
            and isinstance(call.func, ast.Attribute) and call.func.attr == "commit"
            and isinstance(call.func.value, ast.Name))


def _raise_problem(w, st):
    """A refusal's raise: `raise HTTPException(<plain values>)`, no cause."""
    exc = st.exc
    if not (isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name)
            and exc.func.id in _REFUSAL_EXCEPTIONS and st.cause is None):
        w.fail(st, "the raise is not `raise HTTPException(<plain values>)`")
        return
    _plain_args(w, exc, "the raised refusal")


def _returns_other_mode(stmt):
    """Whether `stmt` is `return <refusal>(..., "other_mode")`, awaited or
    not."""
    value = stmt.value if isinstance(stmt, ast.Return) else None
    if isinstance(value, ast.Await):
        value = value.value
    return (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
            and bool(value.args) and isinstance(value.args[-1], ast.Constant)
            and value.args[-1].value == "other_mode")


def refusal_branch_violation(fn, call, form, lookup=None, consts=None):
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
                nothing reachable from _rdm_refuse ending the transaction
                (looked up through `lookup`);
      acquirer  the two acquirers: the same gate form, refused by exactly
                `return False` (the caller rolls back);
      hold      match_hold open and claim: the same gate form, refused at
                once by `await db.rollback()`, and the branch ends by
                returning its "other_mode" refusal, so it never falls
                through into the action; what lies between is the
                refusal's own fresh transaction (the timeouts rearmed,
                the audit row written), walked by _hold_block."""
    w = _Walk(lookup, consts, f"{fn.name} [{form}]")
    stmt = _statement_of(fn, call)
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
        if not _is_db_rollback(body[0]):
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
    target = stmt.targets[0] if isinstance(stmt, ast.Assign) else None
    value = getattr(stmt, "value", None)
    if not (isinstance(value, ast.Await) and value.value is call
            and isinstance(target, ast.Tuple) and target.elts
            and all(isinstance(e, ast.Name) for e in target.elts)):
        return "the gate's answer is not unpacked into a name"
    flag = target.elts[0].id
    branch = _next_statement(fn, stmt)
    test = getattr(branch, "test", None)
    if not (isinstance(branch, ast.If) and isinstance(test, ast.UnaryOp)
            and isinstance(test.op, ast.Not)
            and isinstance(test.operand, ast.Name) and test.operand.id == flag):
        return f"the gate's answer is not refused at once by `if not {flag}:`"
    first = branch.body[0]
    if form == "hold":
        if not _is_db_rollback(first):
            return "the refusal branch does not open with await db.rollback()"
        if not _returns_other_mode(branch.body[-1]):
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
    refused = _is_refusal_exit(first)
    if not (refused is not None and refused.args
            and isinstance(refused.args[-1], ast.Constant)
            and refused.args[-1].value == "other_mode"):
        return ('the refusal branch does not open with '
                'return await _rdm_refuse(..., "other_mode")')
    w.shape("direct: exit, return await _rdm_refuse(...)")
    _refusal_exit_problem(w, first, refused)
    return w.problems[0] if w.problems else _after_exit(branch)


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
    consts = {k: v for k, v in vars(main).items() if isinstance(v, str)}
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
            why = refusal_branch_violation(functions[name], call, form,
                                           _main_def, consts)
            assert why is None, (name, site, form, why)

    open_source = inspect.getsource(match_hold.match_hold_open)
    claim_source = inspect.getsource(match_hold.match_hold_claim)
    for name, source in (("open", open_source), ("claim", claim_source)):
        fn = ast.parse(textwrap.dedent(source)).body[0]
        calls = [node for node in ast.walk(fn)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                 and node.func.id == "_lease_admission_gate"]
        assert [c.func.id for c in calls] == ["_lease_admission_gate"], (name, calls)
        # The loser rolls back its whole transaction first (H3), in the
        # branch that refuses, not somewhere in the function.
        why = refusal_branch_violation(fn, calls[0], "hold")
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


# Round 2's programs (rehearsal-four round 2, findings 6 to 9) and the
# ruling's generic control (a construct the walks never met: a lambda call, a
# match statement, a walrus), each refused by the closed walks for its own
# reason.  Literals only, so a replay reads them with ast.literal_eval and
# runs the same programs against another walk.  R2_HELPER_LINES are the
# helpers they await; R2_CONSTS the module strings their SQL names.
R2_HELPER_LINES = [
    "async def _rdm_attempt(db, lid, pid, n, kind, at, outcome, reason=None):",
    "    await db.execute(text(_RDM_ATTEMPT_SQL), {'lid': lid})",
    "async def _rdm_refuse(ctx, pid, reason, *rest):",
    "    await _rdm_attempt(ctx.db, ctx.lid, pid, 1, 'claim', ctx.now, 'refused', reason)",
    "    return {'readmit': {'status': 'refused', 'reason': reason}}",
    "async def _rdm_end_hold(ctx, pid):",
    "    await ctx.db.execute(text('UPDATE ffa_assembly_seats SET hold_n = NULL'), {})",
    "async def lapse_then_none(ctx, pid):",
    "    if ctx.closed:",
    "        return await _rdm_refuse(ctx, pid, 'lobby_closed')",
    "    if ctx.late:",
    "        await _rdm_end_hold(ctx, pid)",
    "        return None",
    "        return await _rdm_refuse(ctx, pid, 'hold_lapsed')",
    "    return None",
    "async def row_of(ctx, pid):",
    "    return (await ctx.db.execute(text('SELECT * FROM t WHERE id = :p'), {})).first()",
]
R2_CONSTS = {"_RDM_ATTEMPT_SQL": "INSERT INTO ffa_readmit_attempts (n) SELECT 1",
             "_QUOTED_FN_SQL": 'SELECT "lo_create"(0)'}
_R2_GATE = "admitted, _ = await _lease_admission_gate(ctx.db, [pid], 'ffa', ctx.lid)"
_R2_REFUSE = ["if not admitted:", "    return await _rdm_refuse(ctx, pid, 'other_mode')"]
_R2_ROW = ["row = await row_of(ctx, pid)", "if row is None:",
           "    return await _rdm_refuse(ctx, pid, 'not_held')"]
# (label, expected problem, the call the walk stops at, lines)
R2_PREFIX_PROGRAMS = [
    ("F6 an UPDATE before _rdm_claim in its dispatch branch",
     "writes before the gate", "_rdm_claim",
     ["if ctx.step == 'claim':",
      "    await ctx.db.execute(text('UPDATE ffa_seat_readmissions SET claimed_at = now()'), {})",
      "    return await _rdm_claim(ctx, pid)", "return None"]),
    ("F6 a commit before _rdm_claim in its dispatch branch",
     "ends the transaction before the gate", "_rdm_claim",
     ["if ctx.step == 'claim':", "    await ctx.db.commit()",
      "    return await _rdm_claim(ctx, pid)", "return None"]),
    ("F7 SQL COMMIT before the gate", "ends the transaction before the gate",
     "_lease_admission_gate",
     _R2_ROW + ["await ctx.db.execute(text('COMMIT'), {})", _R2_GATE] + _R2_REFUSE),
    ("F7 SQL ROLLBACK before the gate", "ends the transaction before the gate",
     "_lease_admission_gate",
     _R2_ROW + ["await ctx.db.execute(text('ROLLBACK'), {})", _R2_GATE] + _R2_REFUSE),
    ("F8 return None after _rdm_end_hold in a refusal-only helper",
     "a non-refusing exit after a write", "_lease_admission_gate",
     ["refused = await lapse_then_none(ctx, pid)", "if refused is not None:",
      "    return refused", _R2_GATE] + _R2_REFUSE),
    ("also: a commit inside _rdm_refuse's arguments at an exit before the gate",
     "an await inside the refusal's arguments", "_lease_admission_gate",
     ["row = await row_of(ctx, pid)", "if row is None:",
      "    return await _rdm_refuse(ctx, await ctx.db.commit(), 'not_held')",
      _R2_GATE] + _R2_REFUSE),
    ("ruling: SELECT lo_create(0) is not a read",
     "the function lo_create is not on the read-only list", "_lease_admission_gate",
     _R2_ROW + ["await ctx.db.execute(text('SELECT lo_create(0)'), {})", _R2_GATE]
     + _R2_REFUSE),
    ("also: a quoted function name is not a read",
     "a quoted function name", "_lease_admission_gate",
     _R2_ROW + ["await ctx.db.execute(text(_QUOTED_FN_SQL), {})", _R2_GATE]
     + _R2_REFUSE),
    ("generic: a lambda call", "Lambda inside", "_lease_admission_gate",
     _R2_ROW + ["x = (lambda: 1)()", _R2_GATE] + _R2_REFUSE),
    ("generic: a match statement", "Match is not a statement shape",
     "_lease_admission_gate",
     _R2_ROW + ["match row:", "    case _:", "        pass", _R2_GATE] + _R2_REFUSE),
    ("generic: a walrus", "NamedExpr inside", "_lease_admission_gate",
     ["if (row := ctx.row) is None:", "    return {'status': 'refused'}", _R2_GATE]
     + _R2_REFUSE),
]
_R2_ACQUIRE = "if (await _lease_acquire_many(db, ids, 'ranked', None, 1)) is False:"
_R2_RAISE = '    raise HTTPException(status_code=503, detail="admission_contended")'
_R2_DIRECT = "admitted, _ = await _lease_admission_gate(db, [pid], 'ffa', None)"
# (label, expected problem, admission callee, form, lines)
R2_BRANCH_PROGRAMS = [
    ("F9 a commit inside _rdm_refuse's arguments",
     "an await inside the refusal's arguments", "_lease_admission_gate", "direct",
     [_R2_DIRECT, "if not admitted:",
      "    return await _rdm_refuse(ctx, await db.commit(), me, 'claim', n, 'other_mode')"]),
    ("F9 an early successful return before the shared branch's final raise",
     "an exit (Return) before the branch's final raise", "_lease_acquire_many",
     "shared", [_R2_ACQUIRE, "    await db.rollback()",
                "    return {'status': 'formed'}", _R2_RAISE]),
    ("generic: a lambda call in the refusal's arguments", "Lambda inside",
     "_lease_admission_gate", "direct",
     [_R2_DIRECT, "if not admitted:",
      "    return await _rdm_refuse(ctx, (lambda: pid)(), me, 'claim', n, 'other_mode')"]),
    ("generic: a match statement in the hold refusal",
     "Match is not a statement shape", "_lease_admission_gate", "hold",
     [_R2_DIRECT, "if not admitted:", "    await db.rollback()",
      "    match n:", "        case _:", "            pass",
      "    return _refused('other_mode')"]),
    ("generic: a walrus in the shared raise", "NamedExpr inside",
     "_lease_acquire_many", "shared",
     [_R2_ACQUIRE, "    await db.rollback()",
      '    raise HTTPException(status_code=503, detail=(d := "x"))']),
]


def _r2_helpers(extra_lines=()):
    """The R2 helpers (and `extra_lines`) parsed, by name, as a lookup."""
    return {fn.name: fn for fn in ast.parse(chr(10).join(
        list(extra_lines) + R2_HELPER_LINES)).body}.get


def test_h3_refusal_branch_oracle_can_fail():
    """Negative control (#391) for refusal_branch_violation: one planted
    refusal per way a branch can fail its form, beside the shapes that keep
    it, each refused for its own reason."""
    NL = chr(10)

    def why(lines, callee, form):
        fn = ast.parse(NL.join(["async def site(db, ctx, pid, me, n):"]
                               + ["    " + ln for ln in lines])).body[0]
        call = next(node for node in ast.walk(fn)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == callee)
        return refusal_branch_violation(fn, call, form, _r2_helpers(),
                                        R2_CONSTS)

    acquire = "if (await _lease_acquire_many(db, ids, 'ranked', None, 1)) is False:"
    refuse = '    raise HTTPException(status_code=503, detail="admission_contended")'
    later = ["for _ in range(3):", "    pass", "else:", "    await db.rollback()"]
    gate = "admitted, _ = await _lease_admission_gate(db, [pid], 'ffa', None)"
    rdm = '    return await _rdm_refuse(ctx, pid, me, "claim", n, "other_mode")'

    assert why([acquire, "    await db.rollback()", refuse] + later,
               "_lease_acquire_many", "shared") is None
    assert why([gate, "if not admitted:", rdm], GATE, "direct") is None
    assert why([gate, "if not admitted:", "    return False"],
               GATE, "acquirer") is None
    hold = "admitted, now = await _lease_admission_gate(db, [pid], 'ffa', None)"
    assert why([hold, "if not admitted:", "    await db.rollback()",
                "    await _install_database_timeouts(db)",
                '    return _refused("other_mode")'], GATE, "hold") is None
    assert why([hold, "if not admitted:", "    await db.rollback()",
                "    if (await held(db)) is None:",
                '        raise HTTPException(404, "no such hold")',
                '    return await _refuse_attempt(db, 1, "claim", n, "other_mode")'],
               GATE, "hold") is None

    planted = [
        # finding 7 (M1a): the refusal commits; a later rollback answers
        # nothing for it
        ("does not open with await db.rollback()", "_lease_acquire_many",
         "shared", [acquire, "    await db.commit()", refuse] + later),
        ("does not open with await db.rollback()", "_lease_acquire_many",
         "shared", [acquire, refuse] + later),
        ("does not open with await db.rollback()", "_lease_acquire_many",
         "shared", [acquire, "    await note(db)", "    await db.rollback()",
                    refuse]),
        ("awaits or ends a transaction after its rollback",
         "_lease_acquire_many", "shared",
         [acquire, "    await db.rollback()", "    await db.execute(w)", refuse]),
        ("does not end in a raise", "_lease_acquire_many", "shared",
         [acquire, "    await db.rollback()"]),
        ("not tested `is False` by its own if", "_lease_acquire_many",
         "shared", [acquire.replace("is False", "is not False"),
                    "    await db.rollback()", refuse]),
        ("not tested `is False` by its own if", "_lease_acquire_many",
         "shared", ["ok = await _lease_acquire_many(db, ids, 'ranked', None, 1)",
                    "if ok is False:", "    await db.rollback()", refuse]),
        ("does not open with return await _rdm_refuse", GATE, "direct",
         [gate, "if not admitted:", "    pass", rdm.strip()]),
        ("does not open with return await _rdm_refuse", GATE, "direct",
         [gate, "if not admitted:", rdm.replace("other_mode", "other_lobby")]),
        ("is not refused at once by `if not admitted:`", GATE, "direct",
         [gate, "x = 1", "if not admitted:", rdm]),
        ("not unpacked into a name", GATE, "direct",
         ["await _lease_admission_gate(db, [pid], 'ffa', None)",
          "if not admitted:", rdm]),
        ("does not open with return False", GATE, "acquirer",
         [gate, "if not admitted:", "    pass", "return False"]),
        ("does not open with await db.rollback()", GATE, "hold",
         [gate, "if not admitted:", "    await _install_database_timeouts(db)",
          "    await db.rollback()", '    return _refused("other_mode")']),
        # a hold refusal that rolls back and then falls through into the
        # action, or answers another reason
        ('does not end by returning its "other_mode" refusal', GATE, "hold",
         [gate, "if not admitted:", "    await db.rollback()",
          "    await _install_database_timeouts(db)", "    await db.commit()"]),
        ('does not end by returning its "other_mode" refusal', GATE, "hold",
         [gate, "if not admitted:", "    await db.rollback()",
          '    return _refused("lobby_closed")']),
    ]
    for expected, callee, form, lines in planted:
        got = why(lines, callee, form)
        assert got is not None and expected in got, (expected, form, got)
    # Round 2 (findings 9 and the generic control): each program refused by
    # the closed walk for its own reason.
    for label, expected, callee, form, lines in R2_BRANCH_PROGRAMS:
        got = why(lines, callee, form)
        assert got is not None and expected in got, (label, expected, got)
    # The designed refusal must itself keep the transaction: a _rdm_refuse
    # that commits is not the refusal the direct form names.
    committing = ["async def _rdm_refuse(ctx, pid, reason, *rest):",
                  "    await ctx.db.commit()", "    return {}"]
    fn = ast.parse(NL.join(["async def site(db, ctx, pid, me, n):"]
                           + ["    " + ln for ln in [gate, "if not admitted:", rdm]])).body[0]
    call = next(node for node in ast.walk(fn) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name) and node.func.id == GATE)
    got = refusal_branch_violation(fn, call, "direct",
                                   {f.name: f for f in ast.parse(NL.join(committing)).body}.get)
    assert got is not None and "_rdm_refuse is not classified" in got, got


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

def _calls(node, stop):
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == stop for n in ast.walk(node))


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
        elif e[0] == "unread":
            w.fail(st, f"an awaited call before the gate this check does not "
                       f"read ({e[2]})")
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
    refusal = _is_refusal_exit(st)
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
    """The statement that holds the call of `stop`: an if or with walked into
    (its test or items classified, then the statements before the call inside
    the containing branch), or the call as a statement of its own (an
    assignment to names, an expression or a return) with plain arguments."""
    if isinstance(st, ast.If) and not _calls(st.test, stop):
        w.shape("if around the target, walked into")
        if _prefix_effects(w, st, _effects(w, st.test, what="an if's test")):
            w.fail(st, "the answer of a refusing helper is not refused at once")
        branch = st.body if any(_calls(s, stop) for s in st.body) else st.orelse
        _prefix_block(w, branch, stop)
        return
    if isinstance(st, ast.With):
        w.shape("with around the target, walked into")
        for item in st.items:
            _effects(w, item.context_expr, plain_only=True, what="a with item")
        _prefix_block(w, st.body, stop)
        return
    if isinstance(st, (ast.Assign, ast.Expr, ast.Return)):
        value = st.value.value if isinstance(st.value, ast.Await) else st.value
        targets = st.targets if isinstance(st, ast.Assign) else []
        names_only = all(isinstance(t, ast.Name) or (
            isinstance(t, ast.Tuple) and all(isinstance(e, ast.Name) for e in t.elts))
            for t in targets)
        if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                and value.func.id == stop and names_only):
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
        if _calls(st, stop):
            if pending is not None:
                w.fail(st, f"the answer of {pending[1]} is not refused at once")
            _prefix_target(w, st, stop)
            return True
        if top and i == 0 and _is_docstring(st):
            w.shape("docstring")
            continue
        if pending is not None:
            name = pending[0]
            test = getattr(st, "test", None)
            if not (isinstance(st, ast.If) and not st.orelse and len(st.body) == 1
                    and isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
                    and test.left.id == name and len(test.ops) == 1
                    and isinstance(test.ops[0], ast.IsNot)
                    and isinstance(test.comparators[0], ast.Constant)
                    and test.comparators[0].value is None
                    and isinstance(st.body[0], ast.Return)
                    and isinstance(st.body[0].value, ast.Name)
                    and st.body[0].value.id == name):
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
                pending = (st.targets[0].id, refuser)
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


def claim_prefix_violations(stmts, stop, lookup, consts, where="prefix"):
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
    classified the same way.  Anything else is refused, naming its line."""
    w = _Walk(lookup, consts, where)
    if not _prefix_block(w, stmts, stop, top=True):
        w.problems.append(f"no statement calls {stop}")
    return w.problems, w.seen

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
    consts = {k: v for k, v in vars(main).items() if isinstance(v, str)}
    work, claim = _main_def("_asm_readmit_work"), _main_def("_rdm_claim")
    problems, seen_work = claim_prefix_violations(work.body, "_rdm_claim",
                                                  _main_def, consts,
                                                  "_asm_readmit_work")
    assert problems == [], problems
    problems, seen = claim_prefix_violations(claim.body, GATE, _main_def, consts,
                                             "_rdm_claim")
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


def test_h3_claim_prefix_oracle_can_fail():
    """Negative control (#391) for claim_prefix_violations: each planted claim
    breaks the precondition one way and is refused for that reason, beside a
    claim that keeps it (helpers that refuse, read and lock; refusal exits)."""
    NL = chr(10)
    helpers = {fn.name: fn for fn in ast.parse(NL.join([
        "async def reader(ctx, pid):",
        "    return (await ctx.db.execute(text(",
        "        'SELECT 1 FROM t WHERE id = :p FOR UPDATE'), {})).first()",
        "async def writer(ctx, pid):",
        "    await ctx.db.execute(text('UPDATE t SET x = 1'), {})",
        "async def flag(lobby):",
        "    return bool(lobby)",
        "async def live_or_lapse(ctx, pid):",
        "    if ctx.closed:",
        "        return await _rdm_refuse(ctx, pid, 'lobby_closed')",
        "    if ctx.late:",
        "        await ctx.db.execute(text('UPDATE seats SET lapsed = true'), {})",
        "        return await _rdm_refuse(ctx, pid, 'hold_lapsed')",
        "    return None",
        "async def leaky(ctx, pid):",
        "    await ctx.db.execute(text('UPDATE seats SET lapsed = true'), {})",
        "    if ctx.late:",
        "        return await _rdm_refuse(ctx, pid, 'hold_lapsed')",
        "    return None",
    ] + R2_HELPER_LINES)).body}
    consts = {"_WRITE_SQL": "INSERT INTO t VALUES (1)", "_READ_SQL": "SELECT 1",
              **R2_CONSTS}

    def why(lines, stop=GATE):
        fn = ast.parse(NL.join(["async def claim(ctx, pid):"]
                               + ["    " + ln for ln in lines])).body[0]
        return claim_prefix_violations(fn.body, stop, helpers.get, consts)[0]

    gate = "admitted, _ = await _lease_admission_gate(ctx.db, [pid], 'ffa', ctx.lid)"
    refuse = ["if not admitted:", "    return await _rdm_refuse(ctx, pid, 'other_mode')"]
    good = ["refused = await live_or_lapse(ctx, pid)",
            "if refused is not None:", "    return refused",
            "if not await flag(ctx.lobby):", "    return {'status': 'refused'}",
            "row = await reader(ctx, pid)",
            "if row is None:", "    return await _rdm_refuse(ctx, pid, 'not_held')",
            "q = (await ctx.db.execute(text(_READ_SQL), {})).first()"]
    assert why(good + [gate] + refuse) == []

    planted = [
        # item D's mutant: a write placed before the gate
        ("writes before the gate",
         good + ["await ctx.db.execute(text('UPDATE t SET x = 1'), {})", gate] + refuse),
        ("writes before the gate",
         good + ["await ctx.db.execute(text(_WRITE_SQL), {})", gate] + refuse),
        ("writes before the gate",
         good + ["if row.late:", "    await ctx.db.execute(text('DELETE FROM t'), {})",
                 gate] + refuse),
        ("ends the transaction before the gate",
         good + ["await ctx.db.commit()", gate] + refuse),
        ("ends the transaction before the gate",
         good + ["await ctx.db.rollback()", gate] + refuse),
        ("an awaited call before the gate this check does not read",
         good + ["await writer(ctx, pid)", gate] + refuse),
        # a helper that writes outside its refusing branches
        ("an awaited call before the gate this check does not read",
         good + ["await leaky(ctx, pid)", gate] + refuse),
        # SQL the check cannot read
        ("an awaited call before the gate this check does not read",
         good + ["await ctx.db.execute(sql, {})", gate] + refuse),
        ("is not refused at once",
         ["refused = await live_or_lapse(ctx, pid)", gate] + refuse),
        ("is not refused at once",
         ["refused = await live_or_lapse(ctx, pid)", "x = 1",
          "if refused is not None:", "    return refused", gate] + refuse),
        ("an exit before the gate this check does not read",
         good + ["if q is None:", "    return await writer(ctx, pid)", gate] + refuse),
        ("no statement calls _lease_admission_gate", good),
    ]
    for expected, lines in planted:
        got = why(lines)
        assert any(expected in p for p in got), (expected, got)
    # Round 2 (findings 6 to 9, the ruling's lo_create, and the generic
    # control): each program refused by the closed walk for its own reason,
    # beside a dispatch that keeps the precondition.
    assert why(["if ctx.step == 'claim':", "    return await _rdm_claim(ctx, pid)",
                "return None"], "_rdm_claim") == []
    for label, expected, stop, lines in R2_PREFIX_PROGRAMS:
        got = why(lines, stop)
        assert any(expected in p for p in got), (label, expected, got)


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
                await one.commit()
                admitted_two, _ = await asyncio.wait_for(waiting, 2)
                assert not admitted_two
                await two.rollback()

            rows = await case.conn.fetch(
                "SELECT player_id, mode, group_id FROM queue_leases ORDER BY player_id::text")
            assert len(rows) == 2
            assert all(row["mode"] == mode and row["group_id"] == winner for row in rows)

    asyncio.run(inside())
