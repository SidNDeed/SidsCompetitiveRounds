"""MODLOG-1 ruling 4: the census of every route, and the moderator log's one
writer.

A closed walk over main.app.routes (under the pinned FastAPI, learning 465):
every (method, path) has exactly one row in modlog_census.CENSUS, and the
table names no route that does not exist, so a route added later fails here
until it is classed. A route is classed MOD (a moderator action on a player
or on a player's result) or NOT with a reason word from modlog_census.REASONS.

Reach is proved statically. For every MOD row, and every NOT row that names
writers (an action that is no action on a player but records today), each
function the row names holds a direct `_modlog_write(...)` call, and the
route's endpoint reaches that function through the module's call graph
(plain-name calls between module-level functions). The family behaviour is
proved by reading the record back in test_modlog_pg.py.

The writer cannot fail on its own input at run time: every call passes its
action word as a literal of modlog.ACTIONS (or a conditional between such
literals), checked here over the AST of every module that calls it. There is
no other writer of admin_actions in main.py: no AdminAction(...)
constructor call, no soft logger, and the one INSERT INTO admin_actions is the
writer's (admin_evidence._audit, the evidence report's read audit, is the one
other and is named).

Negative controls: for every family, removing the writer calls from one of
its functions makes the reach check fail (test_reach_check_fails_without_*),
and a call whose word is not a literal of the list fails the word check.
"""
from __future__ import annotations

import ast
import copy
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fastapi  # noqa: E402
from fastapi.routing import APIRoute, APIWebSocketRoute  # noqa: E402
from starlette.routing import Mount, Route, WebSocketRoute  # noqa: E402

import main  # noqa: E402
import modlog  # noqa: E402
import modlog_census as C  # noqa: E402

WRITER = "_modlog_write"
MODULE_FILES = {m: os.path.join(API, m + ".py") for m in
                ("main", "admin_evidence", "tournaments", "mail_discord", "match_hold",
                 "auto_logs", "title_ladders")}


def _pinned_fastapi():
    with open(os.path.join(API, "requirements.txt"), encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"\s*fastapi==([0-9.]+)", line)
            if m:
                return m.group(1)
    return None


def _live_routes():
    out = {}

    def walk(routes, prefix=""):
        for r in routes:
            if isinstance(r, Mount):
                walk(r.routes, prefix + r.path)
                continue
            if isinstance(r, (APIWebSocketRoute, WebSocketRoute)):
                out[("WS", prefix + r.path)] = r
                continue
            if isinstance(r, (APIRoute, Route)):
                for m in sorted(r.methods or ()):
                    if m == "HEAD":
                        continue
                    out[(m, prefix + r.path)] = r
    walk(main.app.routes)
    return out


_TREES: dict = {}


def _tree(module):
    if module not in _TREES:
        with open(MODULE_FILES[module], encoding="utf-8") as fh:
            _TREES[module] = ast.parse(fh.read())
    return _TREES[module]


def _functions(tree):
    """name -> FunctionDef for every module-level (async) function."""
    return {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _calls(fn):
    return {n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def _writer_calls(fn):
    return [n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == WRITER]


def _reaches(funcs, start, goal):
    seen, todo = set(), [start]
    while todo:
        name = todo.pop()
        if name == goal:
            return True
        if name in seen or name not in funcs:
            continue
        seen.add(name)
        todo.extend(_calls(funcs[name]))
    return False


def _endpoint_name(route):
    ep = getattr(route, "endpoint", None)
    return getattr(ep, "__name__", None), getattr(ep, "__module__", None)


def reach_failures(tree_by_module=None):
    """Every reach failure of the table, as text lines (empty = all reach)."""
    trees = tree_by_module or {}
    live = _live_routes()
    bad = []
    for key, row in C.CENSUS.items():
        writers = row[2]
        if not writers:
            continue
        name, module = _endpoint_name(live[key])
        funcs = _functions(trees.get(module) or _tree(module))
        for wmod, wfn in writers:
            wfuncs = funcs if wmod == module else _functions(trees.get(wmod) or _tree(wmod))
            fn = wfuncs.get(wfn)
            if fn is None:
                bad.append(f"{key}: {wmod}.{wfn} is not a module-level function")
                continue
            if not _writer_calls(fn):
                bad.append(f"{key}: {wmod}.{wfn} holds no {WRITER}(...) call")
            if wmod == module and not _reaches(funcs, name, wfn):
                bad.append(f"{key}: the endpoint {module}.{name} does not reach {wfn}")
    return bad


def _word_values(node):
    """The literal words an action argument can take, or None when it is not
    made of literals."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        a, b = _word_values(node.body), _word_values(node.orelse)
        return None if a is None or b is None else a | b
    return None


def word_failures(tree_by_module=None):
    trees = tree_by_module or {}
    bad = []
    for module in MODULE_FILES:
        tree = trees.get(module) or _tree(module)
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == WRITER):
                continue
            kws = {k.arg: k.value for k in n.keywords}
            # the session is the one positional argument; the rest by
            # keyword, so the word and the players are read statically
            if len(n.args) != 1 or isinstance(n.args[0], ast.Starred) or None in kws:
                bad.append(f"{module}:{n.lineno} passes other than (db, keywords)")
                continue
            words = _word_values(kws["action"]) if "action" in kws else None
            if words is None:
                bad.append(f"{module}:{n.lineno} action is not a literal word")
            elif not words <= set(modlog.ACTIONS):
                bad.append(f"{module}:{n.lineno} action {sorted(words - set(modlog.ACTIONS))} "
                           f"is not in modlog.ACTIONS")
    return bad


# ---------------------------------------------------------------------------

def test_the_walk_runs_under_the_pinned_fastapi():
    assert fastapi.__version__ == _pinned_fastapi(), (fastapi.__version__, _pinned_fastapi())


def test_every_route_has_exactly_one_class_and_the_table_names_only_live_routes():
    live = _live_routes()
    missing = sorted(set(live) - set(C.CENSUS))
    extra = sorted(set(C.CENSUS) - set(live))
    assert not missing, "routes with no class in modlog_census.CENSUS:\n" + "\n".join(
        f"    ({m!r}, {p!r}): (NOT, '?', ())," for m, p in missing)
    assert not extra, f"rows naming no live route: {extra}"
    for key, row in C.CENSUS.items():
        assert row[0] in (C.MOD, C.NOT), key
        if row[0] == C.MOD:
            assert row[1] in C.FAMILIES and row[2], key
        else:
            assert row[1] in C.REASONS, key


def test_every_moderator_route_and_every_recording_route_reaches_the_writer():
    bad = reach_failures()
    assert not bad, "\n".join(bad)


def test_every_writer_call_passes_a_literal_word_of_the_list():
    bad = word_failures()
    assert not bad, "\n".join(bad)


def test_main_has_no_other_writer_of_admin_actions():
    src = open(MODULE_FILES["main"], encoding="utf-8").read()
    tree = _tree("main")
    funcs = _functions(tree)
    assert "_log_admin_action" not in funcs and "_log_admin_action_strict" not in funcs
    ctor = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name) and n.func.id == "AdminAction"]
    assert ctor == [], ctor
    assert src.count("INSERT INTO admin_actions") == 1
    assert "INSERT INTO admin_actions" in ast.get_source_segment(src, funcs[WRITER])
    for module in MODULE_FILES:
        if module in ("main", "admin_evidence"):
            continue
        assert "INSERT INTO admin_actions" not in open(MODULE_FILES[module], encoding="utf-8").read()
    ev = open(MODULE_FILES["admin_evidence"], encoding="utf-8").read()
    assert ev.count("INSERT INTO admin_actions") == 1   # _audit, the evidence report's read audit


def test_words_that_name_no_player_are_called_without_players_and_420_agrees():
    """modlog.NAMES_NONE: no call of such a word passes `affected`, and
    migration 420's fill of the old rows leaves out exactly these words."""
    bad = []
    for module in MODULE_FILES:
        for n in ast.walk(_tree(module)):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == WRITER:
                kws = {k.arg: k.value for k in n.keywords}
                words = _word_values(kws.get("action")) or set()
                if words & modlog.NAMES_NONE and "affected" in kws:
                    bad.append(f"{module}:{n.lineno}")
    assert not bad, bad
    sql = open(os.path.join(HERE, "..", "sql", "420_admin_actions_modlog.sql"), encoding="utf-8").read()
    m = re.search(r"AND a\.action NOT IN \(([^)]*)\)", sql)
    assert m, "420's fill has no NOT IN list"
    assert set(re.findall(r"'([^']+)'", m.group(1))) == set(modlog.NAMES_NONE)


def test_the_families_and_the_reasons_are_closed():
    assert set(r[1] for r in C.CENSUS.values() if r[0] == C.MOD) == set(C.FAMILIES)
    used = {r[1] for r in C.CENSUS.values() if r[0] == C.NOT}
    assert used <= set(C.REASONS)


def _family_functions():
    fams: dict = {}
    for key, row in C.CENSUS.items():
        if row[0] == C.MOD:
            fams.setdefault(row[1], set()).update(row[2])
    return sorted((fam, sorted(fns)) for fam, fns in fams.items())


def _without_writer(module, fn_name):
    tree = copy.deepcopy(_tree(module))
    fn = _functions(tree)[fn_name]

    class Strip(ast.NodeTransformer):
        def visit_Expr(self, node):
            v = node.value
            if isinstance(v, ast.Await):
                v = v.value
            if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == WRITER:
                return ast.Pass()
            return self.generic_visit(node)
    Strip().visit(fn)
    return tree


@pytest.mark.parametrize("family,functions", _family_functions())
def test_reach_check_fails_without_the_writer_call_of_each_family(family, functions):
    """Mutant per family: one function's writer calls removed, the reach check
    is red (the negative control of the check above)."""
    module, fn_name = functions[0]
    mutated = _without_writer(module, fn_name)
    assert not _writer_calls(_functions(mutated)[fn_name]), "the mutant removed nothing"
    bad = reach_failures({module: mutated})
    assert any(f"{module}.{fn_name} holds no {WRITER}" in b for b in bad), bad


def test_word_check_fails_on_a_word_outside_the_list():
    tree = copy.deepcopy(_tree("main"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == WRITER:
            for k in n.keywords:
                if k.arg == "action":
                    k.value = ast.Constant("not_a_word_of_the_list")
            break
    assert any("not in modlog.ACTIONS" in b for b in word_failures({"main": tree}))
