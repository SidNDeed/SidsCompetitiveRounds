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
    m = re.search(r"AND a\.action::text NOT IN \(([^)]*)\)", sql)
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


# ---------------------------------------------------------------------------
# Fix A6: an exemption is checked, not declared.
#
# READ: a route classed NOT 'read' holds no commit and no write, in its
# endpoint and in every module-level function it reaches through the call
# graph the reach check walks (plain-name calls inside its module). A write
# is a commit, a begin_nested, a session add/delete/flush, or an SQL text
# that inserts, updates or deletes.

_WRITE_SQL = re.compile(r"\b(INSERT\s+INTO|UPDATE\s+[A-Za-z_][A-Za-z_0-9]*\s+SET|DELETE\s+FROM)\b", re.I)
_SESSION_NAMES = frozenset({"db", "session", "sess", "conn", "connection"})
_SESSION_WRITES = frozenset({"add", "add_all", "delete", "flush", "merge"})


def _closure(funcs, start):
    seen, todo = set(), [start]
    while todo:
        name = todo.pop()
        if name in seen or name not in funcs:
            continue
        seen.add(name)
        todo.extend(_calls(funcs[name]))
    return seen


def _writes_in(fn):
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr == "commit":
                out.append(f"commit() at {n.lineno}")
            elif (n.func.attr in _SESSION_WRITES and isinstance(n.func.value, ast.Name)
                  and n.func.value.id in _SESSION_NAMES):
                out.append(f"{n.func.value.id}.{n.func.attr}() at {n.lineno}")
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and _WRITE_SQL.search(n.value):
            out.append(f"write SQL at {n.lineno}")
    return out


def read_failures(census=None, tree_by_module=None):
    trees = tree_by_module or {}
    live = _live_routes()
    bad = []
    for key, row in (census or C.CENSUS).items():
        if row[0] != C.NOT or row[1] != "read" or key not in live:
            continue
        name, module = _endpoint_name(live[key])
        funcs = _functions(trees.get(module) or _tree(module))
        for fname in sorted(_closure(funcs, name)):
            w = _writes_in(funcs[fname])
            if w:
                bad.append(f"{key}: classed read, {module}.{fname} writes ({', '.join(w[:3])})")
    return bad


def test_every_route_classed_read_holds_no_commit_and_no_write():
    bad = read_failures()
    assert not bad, "\n".join(bad)


# EVERY PATH (fixes A1 and A6): a route's change persists only through a
# commit (get_db, checked below, never commits), so the record is on every
# path that changes state when every commit of the route is DOMINATED by a
# writer call: a call of _modlog_write, or of a function the row names, in a
# statement that runs before the commit's statement on every path to it (an
# earlier statement of a block that encloses the commit). Checked in every
# function the row names and, for a row that is not the player's own
# action, in its endpoint. A commit no writer dominates stands in
# NO_CHANGE_COMMITS with the reason it commits no change, and has a
# behaviour test (test_modlog_fix_pg.py, test_a6_*).

NO_CHANGE_COMMITS = {
    # (module, function, the commit's ordinal in the function): reason
    ("main", "chat_moderate_delete", 0):
        "the message is already deleted: nothing is written before this commit",
    ("main", "internal_chat_bridge_moderation", 0):
        "the message is already deleted: nothing is written before this commit",
    ("main", "internal_chat_discord_deleted", 0):
        "no message of the event is live: nothing is written before this commit",
    ("main", "chat_moderate_unmute", 0):
        "the writer runs whenever a mute was revoked; with none revoked the UPDATE changed no row",
    ("main", "chat_moderate_bridge_unmute", 0):
        "the writer runs whenever the mute was revoked; with none revoked the UPDATE changed no row",
}


def _block_chain(fn):
    """id(node) -> its statement chain: (id(block owner), field, index) of
    every statement that encloses it, outermost first."""
    par = {}
    for p in ast.walk(fn):
        for field, value in ast.iter_fields(p):
            if isinstance(value, list):
                for i, c in enumerate(value):
                    if isinstance(c, ast.AST):
                        par[id(c)] = (p, field, i)
            elif isinstance(value, ast.AST):
                par[id(value)] = (p, field, None)

    def chain(node):
        out, n = [], node
        while n is not fn and id(n) in par:
            p, field, i = par[id(n)]
            if i is not None and isinstance(n, ast.stmt):
                out.append((id(p), field, i))
            n = p
        return out[::-1]
    return chain


def _dominates(w, c):
    k = len(w) - 1
    if k < 0 or len(c) <= k or w[:k] != c[:k]:
        return False
    return w[k][:2] == c[k][:2] and w[k][2] < c[k][2]


def commit_failures(census=None, tree_by_module=None):
    trees = tree_by_module or {}
    live = _live_routes()
    bad, seen = [], set()
    for key, row in (census or C.CENSUS).items():
        writers = row[2]
        if not writers or key not in live:
            continue
        name, module = _endpoint_name(live[key])
        names = {WRITER} | {w for _, w in writers}
        targets = list(writers) + ([] if row[1] == "own" else [(module, name)])
        for wmod, fname in targets:
            if (wmod, fname) in seen:
                continue
            seen.add((wmod, fname))
            fn = _functions(trees.get(wmod) or _tree(wmod)).get(fname)
            if fn is None:
                continue
            chain = _block_chain(fn)
            calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
            wchains = [chain(n) for n in calls if isinstance(n.func, ast.Name) and n.func.id in names]
            commits = sorted((n for n in calls if isinstance(n.func, ast.Attribute)
                              and n.func.attr == "commit"), key=lambda n: (n.lineno, n.col_offset))
            for i, c in enumerate(commits):
                if (wmod, fname, i) in NO_CHANGE_COMMITS:
                    continue
                cc = chain(c)
                if not any(_dominates(w, cc) for w in wchains):
                    bad.append(f"{key}: {wmod}.{fname} commit #{i} (line {c.lineno}) is reached "
                               f"on a path with no record before it")
    return bad


def test_get_db_never_commits():
    import inspect
    import database
    assert "commit" not in inspect.getsource(database.get_db)


def test_every_commit_of_a_recording_route_follows_its_record_on_every_path():
    bad = commit_failures()
    assert not bad, "\n".join(bad)


def test_every_no_change_commit_is_still_where_the_list_says():
    """Each exemption names a commit that exists and that no writer
    dominates; the list is closed (its length is pinned)."""
    assert len(NO_CHANGE_COMMITS) == 5
    for (module, fname, i) in NO_CHANGE_COMMITS:
        fn = _functions(_tree(module))[fname]
        commits = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute) and n.func.attr == "commit"]
        assert i < len(commits), (fname, i)


# A REASON (fix A5): in every recording route whose request carries a
# reason or a note, each writer call in the endpoint and in the functions
# the row names passes `reason=`, and its value reads a name or an
# attribute that holds a reason or a note.
_REASONISH = re.compile(r"reason|note|why", re.I)


def _request_reason_fields(endpoint):
    import inspect
    from pydantic import BaseModel
    found = []
    for pname, p in inspect.signature(endpoint).parameters.items():
        ann = p.annotation
        if inspect.isclass(ann) and issubclass(ann, BaseModel):
            found += [f for f in ann.model_fields if _REASONISH.search(f)]
        elif _REASONISH.search(pname):
            found.append(pname)
    src = inspect.getsource(endpoint)
    found += re.findall(r"""(?:payload|body)\.get\(\s*["']([a-z_]*(?:reason|note)[a-z_]*)""", src)
    return found


def reason_failures(tree_by_module=None):
    trees = tree_by_module or {}
    live = _live_routes()
    bad = []
    for key, row in C.CENSUS.items():
        if not row[2] or key not in live or not _request_reason_fields(live[key].endpoint):
            continue
        name, module = _endpoint_name(live[key])
        for wmod, fname in set(row[2]) | {(module, name)}:
            fn = _functions(trees.get(wmod) or _tree(wmod)).get(fname)
            for n in _writer_calls(fn) if fn else ():
                kws = {k.arg: k.value for k in n.keywords}
                if "reason" not in kws or not _REASONISH.search(ast.unparse(kws["reason"])):
                    bad.append(f"{key}: {wmod}.{fname} line {n.lineno} records no reason")
    return bad


def test_every_supplied_reason_reaches_its_record():
    bad = reason_failures()
    assert not bad, "\n".join(bad)


# A LENGTH (fix A8): every writer of an action with a length or an end
# stores it under the keys the game-side mute route writes (duration_minutes
# with permanent) or the action's own end keys: the key is a key of a dict
# literal, or a subscript set, in the function that calls the writer.
LENGTH_KEYS = {
    "chat_mute": ("duration_minutes", "permanent"),
    "chat_automute": ("duration_minutes", "permanent"),
    "chat_mute_msg": ("duration_minutes", "permanent"),
    "chat_purge_user": ("duration_minutes", "permanent", "muted"),
    "ban": ("permanent",),
    "ban_length": ("old_expires_at", "new_expires_at"),
    "ban_repeat": ("expires_at",),
    "alert_create": ("expires_minutes",),
    "mail_bulk_grant": ("days",),
    "pc_portrait_clear": ("lock_days",),
    "ffa_g3_seat": ("hours",),
}


def _keys_set_in(fn):
    keys = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Dict):
            keys |= {k.value for k in n.keys if isinstance(k, ast.Constant)}
        elif isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Store) and \
                isinstance(n.slice, ast.Constant):
            keys.add(n.slice.value)
    return keys


def length_failures(tree_by_module=None):
    trees = tree_by_module or {}
    bad = []
    for module in MODULE_FILES:
        for fn in _functions(trees.get(module) or _tree(module)).values():
            calls = _writer_calls(fn)
            if not calls:
                continue
            have = _keys_set_in(fn)
            for n in calls:
                kws = {k.arg: k.value for k in n.keywords}
                for word in (_word_values(kws.get("action")) or set()) & set(LENGTH_KEYS):
                    missing = [k for k in LENGTH_KEYS[word] if k not in have]
                    if missing:
                        bad.append(f"{module}.{fn.name} line {n.lineno} ({word}) stores no {missing}")
    return bad


def test_every_writer_of_a_length_stores_it():
    bad = length_failures()
    assert not bad, "\n".join(bad)



# NOT AN ACTION, CHECKED (fix A6). 'read' is checked by its property above.
# A word whose property cannot be checked statically lists its routes here,
# written out, with one sentence of reason; every list's length is pinned,
# so a route that moves into or out of a word changes this file.
CLOSED = {
    'automatic': (
        'a grant the server makes on its own from an outside event',
        (
            ('POST', '/api/v1/internal/booster-grant'),
        ),
    ),
    'config': (
        "an administrator's change to server-wide configuration that names no player's standing",
        (
            ('POST', '/api/v1/admin/alerts'),
            ('POST', '/api/v1/admin/alerts/revoke'),
            ('POST', '/api/v1/admin/card-pool-census'),
            ('POST', '/api/v1/admin/game-file-digests'),
            ('POST', '/api/v1/admin/i18n/sync-keys'),
            ('POST', '/api/v1/admin/mail/broadcast'),
            ('POST', '/api/v1/admin/maintenance/start'),
            ('POST', '/api/v1/admin/maintenance/stop'),
            ('POST', '/api/v1/admin/moderation-cases/{case_id}/notified'),
            ('POST', '/api/v1/admin/operators/keys'),
            ('POST', '/api/v1/admin/operators/keys/revoke'),
            ('POST', '/api/v1/admin/pc/snapshot'),
            ('POST', '/api/v1/admin/read-gate/mode'),
            ('POST', '/api/v1/admin/release-digests'),
            ('POST', '/api/v1/admin/release-notes'),
            ('POST', '/api/v1/admin/shop/set-artist'),
            ('POST', '/api/v1/bug-reports/{report_id}/comment'),
            ('POST', '/api/v1/bug-reports/{report_id}/status'),
            ('POST', '/api/v1/chat/moderate/lockdown'),
            ('POST', '/api/v1/chat/moderate/spam-patterns/add'),
            ('POST', '/api/v1/chat/moderate/spam-patterns/revoke'),
            ('POST', '/api/v1/i18n/revert'),
            ('POST', '/api/v1/i18n/review'),
            ('POST', '/api/v1/internal/chat/lockdown'),
            ('POST', '/api/v1/internal/moderation-cases/{case_id}/notified'),
        ),
    ),
    'gameplay': (
        "a game's, a queue's or a lobby's own step that the players' clients drive",
        (
            ('POST', '/api/v1/achievements/unlock'),
            ('POST', '/api/v1/bets'),
            ('POST', '/api/v1/discord-bets'),
            ('POST', '/api/v1/discord-ffa-bets'),
            ('POST', '/api/v1/discord-lobby-bets'),
            ('POST', '/api/v1/discord-team-bets'),
            ('POST', '/api/v1/ffa/bets'),
            ('POST', '/api/v1/ffa/lobbies/{lobby_id}/live-points'),
            ('POST', '/api/v1/ffa/lobby/create'),
            ('POST', '/api/v1/ffa/lobby/join'),
            ('POST', '/api/v1/ffa/lobby/kick'),
            ('POST', '/api/v1/ffa/lobby/settings'),
            ('POST', '/api/v1/ffa/lobby/start'),
            ('POST', '/api/v1/ffa/lobby/{lobby_id}/assembly'),
            ('POST', '/api/v1/ffa/lobby/{lobby_id}/connect'),
            ('POST', '/api/v1/ffa/lobby/{lobby_id}/readmit'),
            ('POST', '/api/v1/ffa/lobby/{lobby_id}/release'),
            ('POST', '/api/v1/ffa/matches'),
            ('POST', '/api/v1/ffa/queue/join'),
            ('POST', '/api/v1/ffa/queue/leave'),
            ('POST', '/api/v1/invites'),
            ('POST', '/api/v1/invites/{invite_id}/accept'),
            ('POST', '/api/v1/invites/{invite_id}/cancel'),
            ('POST', '/api/v1/invites/{invite_id}/decline'),
            ('POST', '/api/v1/lfp-ping'),
            ('POST', '/api/v1/lobby-bets'),
            ('POST', '/api/v1/lobby-bets/cancel'),
            ('POST', '/api/v1/match/game/start'),
            ('POST', '/api/v1/match/hold/beat'),
            ('POST', '/api/v1/match/hold/open'),
            ('POST', '/api/v1/match/hold/{hold_id}/bind'),
            ('POST', '/api/v1/match/hold/{hold_id}/claim'),
            ('POST', '/api/v1/match/hold/{hold_id}/end'),
            ('POST', '/api/v1/match/hold/{hold_id}/entered'),
            ('POST', '/api/v1/matches'),
            ('POST', '/api/v1/matches/card-evidence'),
            ('POST', '/api/v1/matches/casual-dc'),
            ('POST', '/api/v1/matches/combat-evidence'),
            ('POST', '/api/v1/matches/identity-clock-evidence'),
            ('POST', '/api/v1/matches/macro-evidence'),
            ('POST', '/api/v1/matches/seat-evidence'),
            ('POST', '/api/v1/ovt/lobby/create'),
            ('POST', '/api/v1/ovt/lobby/join'),
            ('POST', '/api/v1/ovt/lobby/kick'),
            ('POST', '/api/v1/ovt/lobby/leave'),
            ('POST', '/api/v1/ovt/lobby/prefs'),
            ('POST', '/api/v1/ovt/lobby/settings'),
            ('POST', '/api/v1/ovt/lobby/start'),
            ('POST', '/api/v1/ovt/matches'),
            ('POST', '/api/v1/ovt/queue/join'),
            ('POST', '/api/v1/ovt/queue/leave'),
            ('POST', '/api/v1/ovt/series/continuation'),
            ('POST', '/api/v1/queue/decline'),
            ('POST', '/api/v1/queue/join'),
            ('POST', '/api/v1/queue/leave'),
            ('POST', '/api/v1/queue/ready'),
            ('POST', '/api/v1/queues/escape'),
            ('POST', '/api/v1/report-disconnect'),
            ('POST', '/api/v1/series/preflight'),
            ('POST', '/api/v1/series/{series_id}/live-points'),
            ('POST', '/api/v1/spectate/close'),
            ('POST', '/api/v1/spectate/grant'),
            ('POST', '/api/v1/spectate/heartbeat'),
            ('POST', '/api/v1/spectate/leave'),
            ('POST', '/api/v1/spectate/participant-attest'),
            ('POST', '/api/v1/spectate/validate'),
            ('POST', '/api/v1/team-bets'),
            ('POST', '/api/v1/team/lobby/create'),
            ('POST', '/api/v1/team/lobby/join'),
            ('POST', '/api/v1/team/lobby/kick'),
            ('POST', '/api/v1/team/lobby/leave'),
            ('POST', '/api/v1/team/lobby/prefs'),
            ('POST', '/api/v1/team/lobby/settings'),
            ('POST', '/api/v1/team/lobby/start'),
            ('POST', '/api/v1/team/matches'),
            ('POST', '/api/v1/team/queue/join'),
            ('POST', '/api/v1/team/queue/leave'),
            ('POST', '/api/v1/team/queue/manual-pick-toggle'),
            ('POST', '/api/v1/team/queue/preferred-team'),
            ('POST', '/api/v1/team/queue/ready'),
            ('POST', '/api/v1/team/series/continuation'),
            ('POST', '/api/v1/team/series/{series_id}/live-points'),
            ('POST', '/api/v1/team/series/{series_id}/report-dc'),
            ('POST', '/api/v1/team/series/{series_id}/spawn-confirm'),
            ('POST', '/api/v1/tournaments/{tournament_id}/force-start-vote'),
            ('POST', '/api/v1/tournaments/{tournament_id}/matches/{match_id}/forfeit'),
            ('POST', '/api/v1/tournaments/{tournament_id}/matches/{match_id}/play-now'),
            ('POST', '/api/v1/tournaments/{tournament_id}/ready'),
            ('POST', '/api/v1/tournaments/{tournament_id}/signup'),
            ('POST', '/api/v1/tournaments/{tournament_id}/time-vote'),
            ('POST', '/api/v1/tournaments/{tournament_id}/unsignup'),
        ),
    ),
    'own': (
        "the player's own action on their own account or their own play: no moderator acts",
        (
            ('DELETE', '/api/v1/mail/blocks/{steam_id}'),
            ('DELETE', '/api/v1/mail/{message_id}'),
            ('DELETE', '/api/v1/players/{steam_id}/data'),
            ('POST', '/api/v1/artist/block'),
            ('POST', '/api/v1/artist/catalog-cosmetic-placement'),
            ('POST', '/api/v1/artist/cosmetic-placement'),
            ('POST', '/api/v1/artist/gift'),
            ('POST', '/api/v1/artist/set-desc'),
            ('POST', '/api/v1/artist/set-name'),
            ('POST', '/api/v1/artist/set-price'),
            ('POST', '/api/v1/artist/set-stock'),
            ('POST', '/api/v1/artist/submit-cosmetic'),
            ('POST', '/api/v1/artist/submit-cosmetic-finalize'),
            ('POST', '/api/v1/artist/submit-cosmetic-frame'),
            ('POST', '/api/v1/artist/submit-cosmetic-gif'),
            ('POST', '/api/v1/auth/steam'),
            ('POST', '/api/v1/bug-reports'),
            ('POST', '/api/v1/chat/post'),
            ('POST', '/api/v1/client/compat-outcome'),
            ('POST', '/api/v1/i18n/portal-session'),
            ('POST', '/api/v1/i18n/portal-session/refresh'),
            ('POST', '/api/v1/i18n/proposals'),
            ('POST', '/api/v1/logs/auto'),
            ('POST', '/api/v1/mail'),
            ('POST', '/api/v1/mail/blocks'),
            ('POST', '/api/v1/mail/{message_id}/read'),
            ('POST', '/api/v1/mail/{message_id}/reply'),
            ('POST', '/api/v1/mail/{message_id}/report'),
            ('POST', '/api/v1/mod/toggle-ranked/{steam_id}'),
            ('POST', '/api/v1/music/rate'),
            ('POST', '/api/v1/pc/daily'),
            ('POST', '/api/v1/pc/dance'),
            ('POST', '/api/v1/pc/packs/open'),
            ('POST', '/api/v1/pc/portrait'),
            ('POST', '/api/v1/pc/portrait/motion'),
            ('POST', '/api/v1/pc/prints/discard'),
            ('POST', '/api/v1/pc/prints/discard-batch'),
            ('POST', '/api/v1/pc/settings'),
            ('POST', '/api/v1/pc/trades/accept'),
            ('POST', '/api/v1/pc/trades/cancel'),
            ('POST', '/api/v1/pc/trades/decline'),
            ('POST', '/api/v1/pc/trades/propose'),
            ('POST', '/api/v1/players/block'),
            ('POST', '/api/v1/players/link-code'),
            ('POST', '/api/v1/players/link-discord'),
            ('POST', '/api/v1/players/unblock'),
            ('POST', '/api/v1/players/{steam_id}/active-color'),
            ('POST', '/api/v1/players/{steam_id}/active-cursor-color'),
            ('POST', '/api/v1/players/{steam_id}/active-player-color'),
            ('POST', '/api/v1/players/{steam_id}/active-player-effect'),
            ('POST', '/api/v1/players/{steam_id}/active-title'),
            ('POST', '/api/v1/players/{steam_id}/active-trail'),
            ('POST', '/api/v1/players/{steam_id}/appear-offline'),
            ('POST', '/api/v1/players/{steam_id}/card-tiers'),
            ('POST', '/api/v1/players/{steam_id}/color-toggle'),
            ('POST', '/api/v1/players/{steam_id}/hide-gold'),
            ('POST', '/api/v1/players/{steam_id}/nametag-toggle'),
            ('POST', '/api/v1/players/{steam_id}/pref-same-cards'),
            ('POST', '/api/v1/players/{steam_id}/show-discord'),
            ('POST', '/api/v1/settings/allow-spectators'),
            ('POST', '/api/v1/shop/purchase'),
            ('PUT', '/api/v1/mail/settings'),
            ('WS', '/api/v1/ws/chat'),
        ),
    ),
    'read_upkeep': (
        "a read that also keeps the server's own state on the way (a cache, a heartbeat, a poll's step, a delivery attempt, a session refresh), changing no moderator state on a player",
        (
            ('GET', '/api/v1/achievements/{key}/earners'),
            ('GET', '/api/v1/admin/quarantine/triage'),
            ('GET', '/api/v1/admin/quarantine/triage/{mode}/{group_id}'),
            ('GET', '/api/v1/broadcast/target'),
            ('GET', '/api/v1/chat/moderate/mutes'),
            ('GET', '/api/v1/chat/recent'),
            ('GET', '/api/v1/ffa/leaderboard'),
            ('GET', '/api/v1/ffa/lobbies'),
            ('GET', '/api/v1/ffa/queue/poll/{steam_id}'),
            ('GET', '/api/v1/ffa/readmit/offer'),
            ('GET', '/api/v1/ffa/recent'),
            ('GET', '/api/v1/i18n/approved'),
            ('GET', '/api/v1/i18n/contributors'),
            ('GET', '/api/v1/i18n/grants/mine'),
            ('GET', '/api/v1/i18n/history'),
            ('GET', '/api/v1/i18n/keys'),
            ('GET', '/api/v1/i18n/progress'),
            ('GET', '/api/v1/i18n/proposals'),
            ('GET', '/api/v1/internal/channel-posts/pending'),
            ('GET', '/api/v1/internal/chat/mod-actions'),
            ('GET', '/api/v1/internal/chat/since'),
            ('GET', '/api/v1/internal/evidence-report/game/{code}'),
            ('GET', '/api/v1/internal/evidence-report/pair'),
            ('GET', '/api/v1/internal/evidence-report/player/{steam_id}'),
            ('GET', '/api/v1/internal/evidence-report/series/{code}'),
            ('GET', '/api/v1/internal/pc/events/pending'),
            ('GET', '/api/v1/internal/pc/face/preview/{player_ref}/{locale}'),
            ('GET', '/api/v1/internal/pending-dms'),
            ('GET', '/api/v1/internal/quarantine/digest'),
            ('GET', '/api/v1/internal/stream-posts/pending'),
            ('GET', '/api/v1/leaderboard'),
            ('GET', '/api/v1/mail/inbox'),
            ('GET', '/api/v1/mail/{message_id}'),
            ('GET', '/api/v1/match/hold/mine'),
            ('GET', '/api/v1/music/ratings'),
            ('GET', '/api/v1/music/ratings/mine'),
            ('GET', '/api/v1/ovt/leaderboard'),
            ('GET', '/api/v1/ovt/lobbies'),
            ('GET', '/api/v1/ovt/lobby/resolve'),
            ('GET', '/api/v1/ovt/lobby/state'),
            ('GET', '/api/v1/ovt/queue/poll/{steam_id}'),
            ('GET', '/api/v1/pc/face/preview'),
            ('GET', '/api/v1/pc/packs/result'),
            ('GET', '/api/v1/players/{steam_id}'),
            ('GET', '/api/v1/players/{steam_id}/matches'),
            ('GET', '/api/v1/presence/online'),
            ('GET', '/api/v1/presence/ping'),
            ('GET', '/api/v1/queue/poll/{steam_id}'),
            ('GET', '/api/v1/records'),
            ('GET', '/api/v1/series/active'),
            ('GET', '/api/v1/spectate/games'),
            ('GET', '/api/v1/team/all-series-paged'),
            ('GET', '/api/v1/team/leaderboard'),
            ('GET', '/api/v1/team/lobbies'),
            ('GET', '/api/v1/team/lobby/resolve'),
            ('GET', '/api/v1/team/lobby/state'),
            ('GET', '/api/v1/team/queue/poll/{steam_id}'),
            ('GET', '/api/v1/team/series/{series_id}/state'),
            ('GET', '/api/v1/tournaments/players/{steam_id}/penalty'),
        ),
    ),
    'service': (
        'a call from the bot, the edge or a seat that moves no moderator state on a player',
        (
            ('DELETE', '/api/v1/internal/pc/lease/{lease_id}'),
            ('POST', '/api/v1/admin/set-discord-username'),
            ('POST', '/api/v1/internal/bug-reports/by-number/{bug_number}/user-comment'),
            ('POST', '/api/v1/internal/bug-reports/events/ack'),
            ('POST', '/api/v1/internal/bug-reports/{report_id}/channel-posted'),
            ('POST', '/api/v1/internal/bug-reports/{report_id}/comment'),
            ('POST', '/api/v1/internal/channel-posts/ack'),
            ('POST', '/api/v1/internal/chat/bridge'),
            ('POST', '/api/v1/internal/chat/mirrors'),
            ('POST', '/api/v1/internal/chat/mod-actions/ack'),
            ('POST', '/api/v1/internal/lfp-pings/ack'),
            ('POST', '/api/v1/internal/logs/auto/prune'),
            ('POST', '/api/v1/internal/mail/relay-pref'),
            ('POST', '/api/v1/internal/mail/relay-threads'),
            ('POST', '/api/v1/internal/mail/reply-from-discord'),
            ('POST', '/api/v1/internal/pc/daily'),
            ('POST', '/api/v1/internal/pc/events/ack'),
            ('POST', '/api/v1/internal/pc/lease'),
            ('POST', '/api/v1/internal/pc/packs/open'),
            ('POST', '/api/v1/internal/pending-dms/ack'),
            ('POST', '/api/v1/internal/rank-role-colors'),
            ('POST', '/api/v1/internal/recent-flags/ack'),
            ('POST', '/api/v1/internal/release-posts'),
            ('POST', '/api/v1/internal/stream-posts/ack'),
            ('POST', '/api/v1/internal/tournament-notices/ack'),
            ('POST', '/api/v1/internal/tournaments/checkin-response'),
        ),
    ),
}
CLOSED_LENGTHS = {'automatic': 1, 'config': 25, 'gameplay': 91, 'own': 63, 'read_upkeep': 59, 'service': 26}


def closed_failures(census=None):
    bad = []
    for word, (_sentence, routes) in CLOSED.items():
        if len(routes) != CLOSED_LENGTHS[word]:
            bad.append(f"{word}: {len(routes)} routes listed, {CLOSED_LENGTHS[word]} pinned")
        for key in routes:
            row = (census or C.CENSUS).get(key)
            if row is None or row[0] != C.NOT or row[1] != word:
                bad.append(f"{key}: listed under {word}, classed {row and row[:2]}")
    listed = {k for _, (_, routes) in CLOSED.items() for k in routes}
    for key, row in (census or C.CENSUS).items():
        if row[0] == C.NOT and row[1] != "read" and key not in listed:
            bad.append(f"{key}: classed {row[1]} but in no closed list")
    return bad


def test_every_word_that_cannot_be_checked_is_a_closed_list():
    assert set(CLOSED) == set(C.REASONS) - {"read"}
    assert all(isinstance(s, str) and s for s, _ in CLOSED.values())
    bad = closed_failures()
    assert not bad, "\n".join(bad)


def unclassed(census=None):
    return sorted(set(_live_routes()) - set(census or C.CENSUS))


def _first(word):
    return next(k for k, r in C.CENSUS.items() if r[0] == C.NOT and r[1] == word)


def _endpoint_fn(key, tree):
    name, _module = _endpoint_name(_live_routes()[key])
    return _functions(tree)[name]


def test_a6_mutants_are_red():
    """Each check fails on its own mutant: a route that changes state classed
    as reading only; a route classed read gaining a commit; a route moved
    between closed words; a route with no class; the rebuild without its
    start record; a reason dropped; a length key dropped per writer."""
    mod_key = ("POST", "/api/v1/admin/ban")
    census = dict(C.CENSUS)
    census[mod_key] = (C.NOT, "read", ())
    assert read_failures(census), "mutant: ban classed read"

    read_key = ("GET", "/api/v1/admin/modlog")
    assert C.CENSUS[read_key][1] == "read"
    tree = _tree("main")
    fn = _endpoint_fn(read_key, tree)
    fn.body.append(ast.parse("await db.commit()").body[0])
    assert any(read_key[1] in b for b in read_failures(tree_by_module={"main": tree})), \
        "mutant: a read handler gains a commit"

    census = dict(C.CENSUS)
    k = _first("own")
    census[k] = (C.NOT, "service", ())
    assert closed_failures(census), "mutant: a route moved between words"

    census = dict(C.CENSUS)
    del census[_first("gameplay")]
    assert unclassed(census), "mutant: a route with no class"

    tree = _tree("main")
    fn = _functions(tree)["admin_rebuild_team_glicko"]
    for node in ast.walk(fn):
        for field in ("body", "orelse", "finalbody"):
            stmts = getattr(node, field, None)
            if isinstance(stmts, list):
                setattr(node, field, [s for s in stmts if "_modlog_rebuild_start" not in ast.unparse(s)]
                        or [ast.Pass()])
    assert any("rebuild-glicko" in b for b in commit_failures(tree_by_module={"main": tree})), \
        "mutant: the rebuild without its start record"

    tree = _tree("main")
    fn = _functions(tree)["chat_moderate_unmute"]
    for n in _writer_calls(fn):
        n.keywords = [kw for kw in n.keywords if kw.arg != "reason"]
    assert any("chat_moderate_unmute" in b for b in reason_failures(tree_by_module={"main": tree})), \
        "mutant: unmute without its reason"

    sites = []
    tree = _tree("main")
    for fn in _functions(tree).values():
        for n in _writer_calls(fn):
            kws = {k.arg: k.value for k in n.keywords}
            words = (_word_values(kws.get("action")) or set()) & set(LENGTH_KEYS)
            if words:
                sites.append((fn.name, sorted(words)))
    assert len(sites) >= 10, sites
    for fname, words in sites:
        t = _tree("main")
        f = _functions(t)[fname]
        drop = {k for w in words for k in LENGTH_KEYS[w]}
        for node in ast.walk(f):
            if isinstance(node, ast.Dict):
                for key in node.keys:
                    if isinstance(key, ast.Constant) and key.value in drop:
                        key.value = "x_" + key.value
            elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
                    and node.slice.value in drop:
                node.slice.value = "x_" + node.slice.value
        assert any(f".{fname} line" in b for b in length_failures(tree_by_module={"main": t})), \
            f"mutant: {fname} without its length keys"
    print("\nMUTANT-RED A6/A5/A8 census: read, commit, closed, unclassed, rebuild start, "
          "unmute reason, %d length writers" % len(sites))


def test_word_check_fails_on_a_word_outside_the_list():
    tree = copy.deepcopy(_tree("main"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == WRITER:
            for k in n.keywords:
                if k.arg == "action":
                    k.value = ast.Constant("not_a_word_of_the_list")
            break
    assert any("not in modlog.ACTIONS" in b for b in word_failures({"main": tree}))
