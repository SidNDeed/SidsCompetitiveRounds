"""Bans part 2a, S1/T1/T3: every state-changing route refuses an actively
banned account, by class (the census of ban_sweep_census.py).

The routes are the app's live routes, walked by test_modlog_census's route
walker (_live_routes): every POST, PUT, PATCH and DELETE route, the chat
websocket, and the GETs read_gate.WRITE_ON_GET names. Each handler and each
dependency FastAPI resolves for it is classed from the AST (learning 1035:
the census is derived, the hand lists are asserted equal to it).

The negative controls plant a route of each failing kind and require the
census to name it; the static mutants remove the refusing statements from
one real route of each class (and the banned_ok keyword from one exit) and
require the census to fail on that route.
"""
from __future__ import annotations

import ast
import copy
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import main  # noqa: E402
import read_gate  # noqa: E402
import ban_sweep_census as B  # noqa: E402
from test_modlog_census import _live_routes  # noqa: E402  (the route walker, reused)


def _deps(dependant, out):
    for sub in dependant.dependencies:
        call = sub.call
        if call is not None and hasattr(call, "__name__") and hasattr(call, "__module__"):
            out.append((call.__module__, call.__name__))
        _deps(sub, out)
    return out


def _in_scope(method, path):
    return method in ("POST", "PUT", "PATCH", "DELETE", "WS") or (
        method == "GET" and path in read_gate.WRITE_ON_GET)


_ROWS = None
_FUNCS = None


def _rows_and_funcs():
    global _ROWS, _FUNCS
    if _ROWS is None:
        rows = []
        for (method, path), r in sorted(_live_routes().items()):
            if not _in_scope(method, path):
                continue
            d = getattr(r, "dependant", None)
            rows.append((method, path, r.endpoint.__module__, r.endpoint.__name__,
                         _deps(d, []) if d is not None else []))
        mods = {r[2] for r in rows} | {m for r in rows for m, _ in r[4]}
        funcs = {}
        for m in mods:
            f = os.path.join(API, m + ".py")
            if os.path.exists(f):
                with open(f, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read())
                funcs[m] = {n.name: n for n in tree.body
                            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        _ROWS, _FUNCS = rows, funcs
    return _ROWS, _FUNCS


def test_every_route_in_scope_refuses_a_banned_account_or_is_listed():
    rows, funcs = _rows_and_funcs()
    assert len(rows) > 200, len(rows)          # the walk saw the app
    assert ("WS", "/api/v1/ws/chat") in {(r[0], r[1]) for r in rows}
    bad = B.failures(rows, funcs)
    assert bad == [], "\n".join(bad)


def test_the_banned_ok_callers_are_exactly_the_listed_exits():
    rows, funcs = _rows_and_funcs()
    _, clf = B.census(rows, funcs)
    assert clf.all_soft_ok_callers() == set(B.BANNED_OK), sorted(clf.all_soft_ok_callers())
    for key, why in B.BANNED_OK.items():
        assert why.strip(), key


def _all_rows_and_funcs():
    """Every live route, reads included (the exits' comparison must see a
    route whatever its method), with the same function tables."""
    rows = []
    for (method, path), r in sorted(_live_routes().items()):
        d = getattr(r, "dependant", None)
        rows.append((method, path, r.endpoint.__module__, r.endpoint.__name__,
                     _deps(d, []) if d is not None else []))
    mods = {r[2] for r in rows} | {m for r in rows for m, _ in r[4]}
    funcs = {}
    for m in mods:
        f = os.path.join(API, m + ".py")
        if os.path.exists(f):
            with open(f, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            funcs[m] = {n.name: n for n in tree.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return rows, funcs


def _read_rows():
    """The routes the write census does not walk: every other live route."""
    rows, funcs = _all_rows_and_funcs()
    write_keys = {(r[0], r[1]) for r in _rows_and_funcs()[0]}
    return [r for r in rows if (r[0], r[1]) not in write_keys], funcs


def test_every_registered_route_is_named_in_exactly_one_class():
    """M2: the census sees every registered route, reads included. The write
    census and the READ census together name each live route once."""
    rows, _ = _all_rows_and_funcs()
    w_rows, w_funcs = _rows_and_funcs()
    write, _ = B.census(w_rows, w_funcs)
    r_rows, r_funcs = _read_rows()
    read, _ = B.read_failures(r_rows, r_funcs)
    assert set(write).isdisjoint(read)
    assert set(write) | set(read) == {(r[0], r[1]) for r in rows}
    assert len(read) > 150 and B.READ in set(read.values()), len(read)


def test_no_read_route_reaches_an_unlisted_write():
    r_rows, r_funcs = _read_rows()
    _, bad = B.read_failures(r_rows, r_funcs)
    assert bad == [], "\n".join(bad)
    for key, why in B.READ_WRITES.items():
        assert why.strip(), key


_PLANTED_PAY = '''
async def _planted_pay(db, pid):
    await db.execute(text("UPDATE players SET gold = gold + 100 WHERE id = :p"), {"p": pid})

async def planted_read(pid, db):
    await _planted_pay(db, pid)
    return {"ok": True}
'''


def test_mutant_a_get_route_that_pays_gold_through_a_helper_fails_the_census():
    r_rows, r_funcs = _read_rows()
    funcs = copy.deepcopy(r_funcs)
    for n in ast.parse(_PLANTED_PAY).body:
        funcs["main"][n.name] = n
    key = ("GET", "/api/v1/planted/read")
    rows = r_rows + [(key[0], key[1], "main", "planted_read", [])]
    out, bad = B.read_failures(rows, funcs)
    assert out[key] == B.READ
    assert bad == [f"{key}: a READ route that reaches a writing statement and is not on READ_WRITES"], bad
    # the write census's walk (the route filter it had) never saw such a route
    assert not _in_scope(*key)


def test_an_open_get_route_that_writes_says_what_it_writes():
    """M1: a GET route open to a banned account whose handler reaches a write
    states, in its OPEN_ROUTES reason, what it WRITES."""
    rows, funcs = _rows_and_funcs()
    bad = []
    for method, path, module, name, deps in rows:
        key = (method, path)
        if method != "GET" or key not in B.OPEN_ROUTES:
            continue
        if any(B.reaches(funcs, m, n, B._write_call) for m, n in [(module, name), *deps]):
            if "WRITES" not in B.OPEN_ROUTES[key]:
                bad.append(f"{key}: writes and its reason does not say what")
    assert bad == [], "\n".join(bad)


def test_the_server_exits_equal_ban_r17_both_ways():
    rows, funcs = _all_rows_and_funcs()
    server, bad = B.server_exits(rows, funcs)
    bad = bad + B.exits_vs_r17(server)
    assert bad == [], "\n".join(bad)


def test_negative_control_the_exits_comparison_names_both_directions():
    rows, funcs = _all_rows_and_funcs()
    server, _ = B.server_exits(rows, funcs)
    r17 = dict(B.BAN_R17_EXITS)
    r17.pop(("POST", "/api/v1/queue/leave"))
    r17[("POST", "/api/v1/planted/leave")] = "planted"
    bad = B.exits_vs_r17(server, r17)
    assert any("planted/leave" in b and "not an exit of the server" in b for b in bad), bad
    assert any("/queue/leave" in b and "not on BAN-R17's list" in b for b in bad), bad


def test_mutant_the_decline_without_its_exemption_fails_the_comparison():
    rows, funcs = _all_rows_and_funcs()
    funcs = copy.deepcopy(funcs)
    n = 0
    for call in ast.walk(funcs["main"]["queue_decline"]):
        if isinstance(call, ast.Call) and B._call_name(call)[0] == B.SOFT_CALL:
            call.keywords = [k for k in call.keywords if k.arg != B.BANNED_OK_KW]
            n += 1
    assert n == 1
    server, _ = B.server_exits(rows, funcs)
    assert B.exits_vs_r17(server) == [
        "('POST', '/api/v1/queue/decline'): on BAN-R17's list and not an exit of the server"]


def test_negative_control_a_strict_exit_that_reads_a_ban_is_not_an_exit():
    rows, funcs = _all_rows_and_funcs()
    funcs = copy.deepcopy(funcs)
    fn = funcs["main"]["spectate_leave"]
    fn.body.insert(0, ast.parse("await _ban_gate_or_raise(db, req.steam_id, request)").body[0])
    key = ("POST", "/api/v1/spectate/leave")
    server, bad = B.server_exits(rows, funcs, {key: "planted"})
    assert key not in server
    assert any("reads a ban" in b for b in bad), bad


def test_every_listed_route_has_a_reason():
    for table in (B.OPEN_ROUTES, B.INTERNAL_ONLY):
        for key, why in table.items():
            assert isinstance(why, str) and why.strip(), key
    for key, (cls, calls, why) in B.BY_HAND.items():
        assert cls in (B.BAN, B.ADMIN, B.STRICT) and calls and why.strip(), key


# ---- negative and positive controls: planted routes of each kind ----------

PLANTED = '''
async def gated(request, steam_id, db):
    await _check_steam_session(request, steam_id, db)

async def nogate(db):
    x = 1

async def exemption_only(request, db):
    if await _strict_steam_session_ok(request, "1", db):
        skip = True

async def soft_ok(request, steam_id, db):
    await _check_steam_session(request, steam_id, db, banned_ok=True)

async def internal_alone(x_internal_key):
    _require_internal_key(x_internal_key)

async def conditional(request, steam_id, db, flag):
    if flag:
        await _check_steam_session(request, steam_id, db)

async def signature_alone(steam_id, sig):
    if not _verify_admin_hmac(steam_id, "a", "b", sig):
        raise HTTPException(403)

async def admin_both(db, steam_id, sig):
    if not await _is_admin(db, steam_id):
        raise HTTPException(403)
    if not _verify_admin_hmac(steam_id, "a", "b", sig):
        raise HTTPException(403)

async def ban_read(db, steam_id):
    if await _is_banned(db, steam_id):
        raise HTTPException(409)

async def hand_missing(db):
    x = 1
'''


def _planted():
    tree = ast.parse(PLANTED)
    funcs = {"planted": {n.name: n for n in tree.body}}
    rows = [("POST", f"/planted/{n}", "planted", n, []) for n in funcs["planted"]]
    return rows, funcs


def _fails(**kw):
    rows, funcs = _planted()
    args = dict(open_routes={}, internal_only={}, banned_ok={}, by_hand={})
    args.update(kw)
    return B.failures(rows, funcs, **args)


def _named(bad, key):
    return [b for b in bad if b.startswith(repr(key)) or repr(key) in b]


@pytest.mark.parametrize("name", ["nogate", "exemption_only", "soft_ok", "conditional",
                                  "signature_alone", "hand_missing"])
def test_negative_control_a_planted_ungated_route_fails_the_census(name):
    bad = _named(_fails(), ("POST", f"/planted/{name}"))
    assert any("refuses no banned account" in b for b in bad), (name, bad)


@pytest.mark.parametrize("name", ["gated", "admin_both", "ban_read"])
def test_positive_control_a_planted_gated_route_is_silent(name):
    assert _named(_fails(), ("POST", f"/planted/{name}")) == []


def test_negative_control_an_unlisted_banned_ok_caller_fails():
    assert any("('planted', 'soft_ok'): calls the soft check with banned_ok" in b for b in _fails())


def test_negative_control_an_unlisted_internal_alone_route_fails():
    bad = _named(_fails(), ("POST", "/planted/internal_alone"))
    assert any("INTERNAL alone" in b for b in bad), bad


def test_negative_control_stale_entries_fail():
    bad = _fails(open_routes={("POST", "/gone"): "x"}, internal_only={("POST", "/gone2"): "x"},
                 banned_ok={("planted", "gone"): "x"}, by_hand={("POST", "/gone3"): (B.BAN, ("x",), "x")})
    assert any("('POST', '/gone'): an OPEN_ROUTES entry no route matches" in b for b in bad), bad
    assert any("('POST', '/gone2'): an INTERNAL_ONLY entry no route matches" in b for b in bad), bad
    assert any("('planted', 'gone'): in BANNED_OK but makes no banned_ok call" in b for b in bad), bad
    assert any("('POST', '/gone3'): a BY_HAND entry no route matches" in b for b in bad), bad


def test_negative_control_an_open_entry_on_a_gated_route_fails():
    bad = _fails(open_routes={("POST", "/planted/gated"): "x"})
    assert any("is in OPEN_ROUTES but is classed SOFT" in b for b in bad), bad


def test_negative_control_a_hand_entry_whose_call_is_absent_adds_nothing():
    key = ("POST", "/planted/hand_missing")
    bad = _fails(by_hand={key: (B.BAN, ("_is_banned_via_session",), "x")})
    assert any("refuses no banned account" in b for b in _named(bad, key)), bad


# ---- T3: static mutants, one per class and one for banned_ok -------------

def _strip_gates(funcs, module, name):
    """A copy of funcs in which module.name has lost every top-level statement
    that carries a class."""
    out = {m: dict(fs) for m, fs in funcs.items()}
    fn = copy.deepcopy(out[module][name])
    keep = []
    for st in fn.body:
        probe = copy.deepcopy(fn)
        probe.body = [st]
        out[module][name] = probe
        if not B.Classifier(out).classes(module, name):
            keep.append(st)
    fn.body = keep or [ast.Pass()]
    out[module][name] = fn
    return out


@pytest.mark.parametrize("cls", [B.STRICT, B.SOFT, B.BAN, B.ADMIN, B.INTERNAL])
def test_mutant_a_route_without_its_gate_fails_the_census(cls):
    rows, funcs = _rows_and_funcs()
    result, _ = B.census(rows, funcs)
    cands = [r for r in rows if result[(r[0], r[1])][1] == (cls,)
             and (r[0], r[1]) not in B.BY_HAND]
    assert cands, cls
    method, path, module, name, deps = cands[0]
    mutant = _strip_gates(funcs, module, name)
    for dmod, d in deps:
        if d in mutant.get(dmod, {}):
            mutant = _strip_gates(mutant, dmod, d)
    bad = B.failures(rows, mutant)
    assert any(b.startswith(repr((method, path))) for b in bad), (cls, method, path, bad)


def test_mutant_an_exit_without_banned_ok_fails_the_census():
    rows, funcs = _rows_and_funcs()
    out = {m: dict(fs) for m, fs in funcs.items()}
    fn = copy.deepcopy(out["main"]["queue_leave"])
    hit = 0
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            for k in n.keywords:
                if k.arg == "banned_ok":
                    k.value = ast.Constant(False)
                    hit += 1
    assert hit == 1, hit
    out["main"]["queue_leave"] = fn
    bad = B.failures(rows, out)
    assert any("('main', 'queue_leave'): in BANNED_OK but makes no banned_ok call" in b for b in bad), bad
    assert any("('POST', '/api/v1/queue/leave'): is in OPEN_ROUTES but is classed SOFT" in b
               for b in bad), bad


# ---- the exits' keyword reaches every test stand-in of the soft check ----
#
# The exits call _check_steam_session(..., banned_ok=True). A test that puts
# its own function in as main._check_steam_session takes the place of the real
# one for every route, the exits too; a stand-in that cannot take banned_ok
# raises TypeError at the first exit it meets.


def _patched_values(tree) -> list:
    """Every expression a file puts in as main._check_steam_session."""
    out = []
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "setattr" and len(n.args) >= 3
                and isinstance(n.args[0], ast.Name) and n.args[0].id == "main"
                and isinstance(n.args[1], ast.Constant)
                and n.args[1].value == "_check_steam_session"):
            out.append(n.args[2])
        elif (isinstance(n, ast.Assign) and len(n.targets) == 1
              and isinstance(n.targets[0], ast.Attribute)
              and n.targets[0].attr == "_check_steam_session"
              and isinstance(n.targets[0].value, ast.Name)
              and n.targets[0].value.id == "main"):
            out.append(n.value)
    return out


def _stub_names_patched_into_main(tree) -> set:
    out = set()
    for v in _patched_values(tree):
        name = v.attr if isinstance(v, ast.Attribute) else getattr(v, "id", None)
        if name:
            out.add(name)
    return out


# FIX-1 M3: the guard judges what a stand-in DOES with the keywords. A name a
# file patches in that is bound to a function must READ its banned_ok or its
# **kwargs (record or forward them); taking them and dropping them is a
# finding. A name bound to soft_check_standin.SoftCheckStandIn(...) records
# every keyword and passes. FIX-1B point 5: the binding is found where it is
# made, in another file too (`hold_test._fake_session`, `H._fake_session`
# through `H = R.hold_test`); a name bound to the value main._check_steam_session
# held before (test_ffa_assembly_pg's `noop` and `_REAL_SESSION_CHECK`) puts
# back the object that stood there, which is the real check or a stand-in
# whose own patch is judged where it is made. A value whose binding cannot be
# found is a finding. Listed: stand-ins that drop banned_ok on purpose.
STANDIN_DROPS_OK = {
    ("test_ban_sweep_live.py", "without_banned_ok"):
        "the S2 mutant: drops banned_ok on purpose to show that the exit then refuses",
}

_TREES = {}


def _tree(sources, fname):
    key = (fname, hash(sources[fname]))
    if key not in _TREES:
        _TREES[key] = ast.parse(sources[fname])
    return _TREES[key]


def _resolve_module(sources, fname, alias, depth=0):
    """The file an alias names in fname: `import x as alias`, `import alias`,
    or `alias = other.attr` where other names a module."""
    if fname not in sources or depth > 4:
        return None
    for n in ast.walk(_tree(sources, fname)):
        if isinstance(n, ast.Import):
            for a in n.names:
                if (a.asname or a.name) == alias and a.name + ".py" in sources:
                    return a.name + ".py"
        elif (isinstance(n, ast.Assign) and len(n.targets) == 1
              and isinstance(n.targets[0], ast.Name) and n.targets[0].id == alias
              and isinstance(n.value, ast.Attribute) and isinstance(n.value.value, ast.Name)):
            base = _resolve_module(sources, fname, n.value.value.id, depth + 1)
            if base:
                return _resolve_module(sources, base, n.value.attr, depth + 1)
    return None


def _is_soft_check_value(v):
    return (isinstance(v, ast.Attribute) and v.attr == "_check_steam_session"
            and isinstance(v.value, ast.Name) and v.value.id == "main")


def _judge_def(fn):
    a = fn.args
    kw = ([a.kwarg.arg] if a.kwarg else []) + [x.arg for x in a.args + a.kwonlyargs if x.arg == "banned_ok"]
    read = {x.id for x in ast.walk(fn) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)}
    return "reads banned_ok" if any(k in read for k in kw) else "drops banned_ok"


def _bindings(sources, fname, name, depth=0):
    """[(file, name, verdict)] for every binding of `name` in fname."""
    out = []
    if fname not in sources or depth > 4:
        return [(fname, name, "unresolved")]
    for n in ast.walk(_tree(sources, fname)):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            out.append((fname, name, _judge_def(n)))
        elif isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets):
            v = n.value
            if isinstance(v, ast.Call) and B._name_of(v) == "SoftCheckStandIn":
                out.append((fname, name, "records"))
            elif _is_soft_check_value(v):
                out.append((fname, name, "restore"))
            elif isinstance(v, ast.Name):
                out += _bindings(sources, fname, v.id, depth + 1)
            else:
                out.append((fname, name, "unresolved"))
        elif isinstance(n, ast.ImportFrom) and n.module and n.module + ".py" in sources:
            for a in n.names:
                if (a.asname or a.name) == name:
                    out += _bindings(sources, n.module + ".py", a.name, depth + 1)
    return out or [(fname, name, "unresolved")]


def _standin_verdicts(sources: dict) -> list:
    """[(file of the binding, name, verdict)] for every value any file puts in
    as main._check_steam_session, each binding judged where it is made."""
    out = set()
    for fname in sorted(sources):
        for v in _patched_values(_tree(sources, fname)):
            if isinstance(v, ast.Name):
                out.update(_bindings(sources, fname, v.id))
            elif isinstance(v, ast.Attribute) and isinstance(v.value, ast.Name):
                mod = _resolve_module(sources, fname, v.value.id)
                out.update(_bindings(sources, mod, v.attr) if mod else [(fname, ast.unparse(v), "unresolved")])
            else:
                out.add((fname, ast.unparse(v), "unresolved"))
    return sorted(out)


def _stubs_without_banned_ok(sources: dict, allowed=None) -> list:
    """(file, name) for every stand-in binding that drops banned_ok or cannot
    be found, unless listed in STANDIN_DROPS_OK."""
    allowed = STANDIN_DROPS_OK if allowed is None else allowed
    return sorted({(f, n) for f, n, v in _standin_verdicts(sources)
                   if v in ("drops banned_ok", "unresolved") and (f, n) not in allowed})


def _standin_bindings(sources: dict) -> list:
    """(file, name) for every name bound to SoftCheckStandIn(...)."""
    out = []
    for fname, src in sorted(sources.items()):
        for n in ast.walk(ast.parse(src)):
            if (isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                    and B._name_of(n.value) == "SoftCheckStandIn"):
                out += [(fname, t.id) for t in n.targets if isinstance(t, ast.Name)]
    return out


def _test_sources() -> dict:
    out = {}
    for fname in sorted(os.listdir(HERE)):
        if fname.endswith(".py"):
            with open(os.path.join(HERE, fname), encoding="utf-8") as fh:
                out[fname] = fh.read()
    return out


def test_every_stand_in_for_the_soft_check_takes_banned_ok():
    sources = _test_sources()
    patched = sum(len(_stub_names_patched_into_main(ast.parse(s))) for s in sources.values())
    assert patched >= 15, patched   # the walk finds the stand-ins it is about
    assert _stubs_without_banned_ok(sources) == []
    assert len(_standin_bindings(sources)) >= 20, _standin_bindings(sources)


def test_negative_control_a_stand_in_without_banned_ok_is_named():
    planted = {
        "planted_a.py": ("async def stub(request, steam_id, db):\n    return None\n"
                         "monkeypatch.setattr(main, '_check_steam_session', stub)\n"),
        "planted_b.py": ("async def stub2(request, steam_id, db, **_kw):\n    return None\n"
                         "main._check_steam_session = stub2\n"),
        "planted_c.py": ("async def stub3(request, steam_id, db, **kw):\n    return await rec(**kw)\n"
                         "main._check_steam_session = stub3\n"
                         "stub4 = SoftCheckStandIn()\nmain._check_steam_session = stub4\n"),
    }
    # planted_b takes **_kw and drops it: the form the no-op stand-ins had (M3)
    assert _stubs_without_banned_ok(planted) == [("planted_a.py", "stub"), ("planted_b.py", "stub2")]
    assert _standin_bindings(planted) == [("planted_c.py", "stub4")]


def test_the_stand_ins_bound_in_another_file_and_the_assembly_restore_are_judged():
    v = _standin_verdicts(_test_sources())
    assert ("test_match_hold_pg.py", "_fake_session", "records") in v, v
    assert ("test_ffa_assembly_pg.py", "noop", "restore") in v, v
    assert ("test_ffa_assembly_pg.py", "_REAL_SESSION_CHECK", "restore") in v, v
    assert not [x for x in v if x[2] == "unresolved"], v


def test_mutant_a_stand_in_bound_in_another_file_that_drops_banned_ok_is_named():
    planted = {
        "planted_helpers.py": "async def fake(request, steam_id, db, **_kw):\n    return None\n",
        "planted_user.py": ("import planted_helpers as hx\n"
                            "monkeypatch.setattr(main, '_check_steam_session', hx.fake)\n"),
        "planted_chain.py": ("import planted_user as U\nH = U.hx\n"
                             "main._check_steam_session = H.fake\n"),
        "planted_odd.py": "main._check_steam_session = make_stub()\n",
    }
    assert _stubs_without_banned_ok(planted) == [
        ("planted_helpers.py", "fake"), ("planted_odd.py", "make_stub()")]
    assert _standin_verdicts(planted).count(("planted_helpers.py", "fake", "drops banned_ok")) == 1


def test_negative_control_the_deliberate_mutant_is_listed():
    sources = {f: s for f, s in _test_sources().items() if f == "test_ban_sweep_live.py"}
    assert _stubs_without_banned_ok(sources, allowed={}) == [("test_ban_sweep_live.py", "without_banned_ok")]


# -- F2 a: every status a record table is written with is classed once --------

_RECORD_TABLES = ("ffa_lobbies", "ranked_series", "team_series", "ovt_series")


def _written_statuses(sources):
    """{table: {status word}}: each word an UPDATE ... SET status = '<w>' or an
    INSERT INTO <table> statement's literal writes, over the api modules'
    string constants, plus each ORM model's status default."""
    import re as _re
    out = {t: set() for t in _RECORD_TABLES}
    for src in sources.values():
        for n in ast.walk(ast.parse(src)):
            if not (isinstance(n, ast.Constant) and isinstance(n.value, str)):
                continue
            for t in _RECORD_TABLES:
                for m in _re.finditer(r"UPDATE\s+" + t + r"\b(?:\s+\w+)?\s+SET\b(.*?)(?:\bWHERE\b|$)",
                                      n.value, _re.S | _re.I):
                    out[t].update(_re.findall(r"\bstatus\s*=\s*'(\w+)'", m.group(1)))
                for m in _re.finditer(r"INSERT\s+INTO\s+" + t + r"\b(.*?)(?:;|$)", n.value, _re.S | _re.I):
                    out[t].update(_re.findall(r"'(\w+)'", m.group(1)))
    import models
    for cls in vars(models).values():
        tbl = getattr(cls, "__tablename__", None)
        if tbl in out and "status" in getattr(cls, "__table__").c:
            col = cls.__table__.c.status
            for d in (getattr(col.default, "arg", None),
                      getattr(getattr(col.server_default, "arg", None), "text", None)):
                if isinstance(d, str):
                    out[tbl].add(d.strip("'"))
    return out


def _api_sources():
    out = {}
    for fname in sorted(os.listdir(API)):
        if fname.endswith(".py"):
            with open(os.path.join(API, fname), encoding="utf-8") as fh:
                out[fname] = fh.read()
    return out


def test_every_written_record_status_is_classed_live_or_terminal():
    written = _written_statuses(_api_sources())
    classes = main.BAN_RECORD_STATUSES
    assert set(classes) == set(_RECORD_TABLES)
    bad = [f"{t}: '{w}' is written and BAN_RECORD_STATUSES does not class it"
           for t in _RECORD_TABLES for w in sorted(written[t] - set(classes[t]))]
    assert bad == [], "\n".join(bad)
    assert all(c in ("live", "terminal", "open_lobby") for t in classes for c in classes[t].values())
    assert all(written[t] for t in _RECORD_TABLES), written     # the collector saw each table


def test_negative_control_a_new_status_word_turns_the_status_census_red():
    planted = {"planted.py": "X = \"UPDATE team_series SET status = 'parked_forever' WHERE id = :i\""}
    written = _written_statuses(planted)
    assert "parked_forever" in written["team_series"]
    assert "parked_forever" not in main.BAN_RECORD_STATUSES["team_series"]


def test_the_void_discovery_reads_the_live_statuses_of_every_table():
    import inspect
    src = inspect.getsource(main._ban_void_lock)
    for t in _RECORD_TABLES:
        assert f'_ban_live_statuses_sql("{t}")' in src, t
    assert "status = 'active'" not in src and "'dc_paused'" not in src


# ---- F4: every sweep ban read under the shared identity lock -------------

def _api_modules():
    return {f[:-3]: s for f, s in _api_sources().items()}


def test_every_sweep_gate_read_is_under_the_identity_lock_or_a_listed_row_lock():
    bad = B.unlocked_gate_reads(_api_modules())
    assert bad == [], "\n".join(bad)


def test_no_row_lock_is_written_before_the_identity_lock():
    bad = B.row_locks_before_the_gate(_api_modules())
    assert bad == [], "\n".join(bad)


_PLANTED_F4 = '''
async def planted_direct(db, steam_id):
    await _ban_gate_or_raise(db, steam_id)

async def planted_row_first(db, sid):
    await db.execute(text("SELECT 1 FROM series WHERE id = :i FOR NO KEY UPDATE"), {"i": sid})
    await _ban_lock_and_gate(db, [sid])
'''


def test_mutant_a_route_reading_the_ban_without_the_lock_fails_the_census():
    mods = _api_modules()
    mods["main"] = mods["main"] + _PLANTED_F4
    bad = B.unlocked_gate_reads(mods)
    assert bad == ["main.planted_direct: 1 ban read(s) outside _ban_lock_and_gate, 0 listed"], bad


def test_mutant_a_row_lock_before_the_identity_lock_fails_the_census():
    mods = _api_modules()
    mods["main"] = mods["main"] + _PLANTED_F4
    bad = B.row_locks_before_the_gate(mods)
    assert len(bad) == 1 and bad[0].startswith("main.planted_row_first: a row lock at line"), bad


def test_negative_control_the_row_serialized_entry_is_load_bearing():
    bad = B.unlocked_gate_reads(_api_modules(), row_serialized={})
    # every entry is load-bearing: the 2v2 DC report, and the 1v2 and 2v2
    # report routes' plain pre-checks (FIX-1B point 3)
    assert sorted(bad) == sorted(
        "main.%s: 1 ban read(s) outside _ban_lock_and_gate, 0 listed" % n
        for n in ("team_series_report_dc", "submit_ovt_match", "submit_team_match")), bad
    assert set(B.ROW_SERIALIZED) == {("main", "team_series_report_dc"), ("main", "submit_ovt_match"),
                                     ("main", "submit_team_match")}, sorted(B.ROW_SERIALIZED)
    bad = B.row_locks_before_the_gate(_api_modules(), ok={})
    assert [b.split(":")[0] for b in bad] == ["main.link_discord"], bad


class _RecDb:
    def __init__(self):
        self.calls = []

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), dict(params or {})))

        class _R:
            def all(self):
                return []

            def mappings(self):
                return self

            def scalar(self):
                return None
        return _R()


def _lock_order_failures(helper):
    """The helper's locks for ids of two lengths and an actor: every id and
    the actor, in the ONE identity order, all before the ban read."""
    import asyncio
    from identity_order import identity_lock_key
    db = _RecDb()
    ids, actor = ["9000000000000002", "90000000000000001"], "1000000000000003"
    asyncio.run(helper(db, ids, None, actor=actor))
    locks = [p["sid"] for s, p in db.calls if "pg_advisory_xact_lock" in s]
    want = sorted({*ids, actor}, key=identity_lock_key)
    bad = []
    if locks != want:
        bad.append(f"locks {locks} != {want}")
    reads = [i for i, (s, _p) in enumerate(db.calls) if "player_bans" in s]
    if not reads or reads[0] < len(locks):
        bad.append(f"ban read at {reads} before the locks end ({len(locks)})")
    return bad


def test_the_helper_locks_every_id_and_the_actor_in_the_canonical_order():
    assert _lock_order_failures(main._ban_lock_and_gate) == []


def _mutant_helper(old, new):
    import inspect
    import textwrap
    src = textwrap.dedent(inspect.getsource(main._ban_lock_and_gate))
    assert src.count(old) == 1, old
    ns = dict(vars(main))
    exec(compile(src.replace(old, new), "<mutant>", "exec"), ns)
    return ns["_ban_lock_and_gate"]


@pytest.mark.parametrize("old,new", [
    ("[*(steam_ids or ()), actor, *(exclusive or ())]", "[*(steam_ids or ()), *(exclusive or ())]"),
    ("key=identity_lock_key)", "key=None)"),
])
def test_mutant_the_helper_without_the_actor_or_the_canonical_order_fails(old, new):
    assert _lock_order_failures(_mutant_helper(old, new)) != []


# ---- FIX-1B point 3: ONE order for every taker of the identity key ----------
#
# Made-up ids of 4, 8 (a word), 16, 17, 18, 19 and 20 characters. Bare sorted()
# and the one key disagree on them, which is why one key must serve all takers.

_MIXED = ["90000000000000000019", "9000", "900000000000000018", "steamwrd",
          "1000000000000000017", "9000000000000016", "10000000000000017"]
_MIXED_ORDER = ["9000", "steamwrd", "9000000000000016", "10000000000000017",
                "900000000000000018", "1000000000000000017", "90000000000000000019"]


def test_the_one_identity_key_is_total_for_any_text():
    from identity_order import identity_lock_key
    assert sorted(_MIXED, key=identity_lock_key) == _MIXED_ORDER
    assert sorted(reversed(_MIXED), key=identity_lock_key) == _MIXED_ORDER
    digits = [x for x in _MIXED if x.isdigit()]
    assert sorted(digits, key=identity_lock_key) == sorted(digits, key=int)
    assert sorted(_MIXED) != _MIXED_ORDER          # bare sorted() orders them otherwise
    assert identity_lock_key("") == (0, "") and identity_lock_key(None) == (0, "")
    assert sorted(["", "a", "0"], key=identity_lock_key) == ["", "0", "a"]
    assert identity_lock_key(9000) == identity_lock_key("9000")
    assert main._ffa_sort_key("steamwrd") == identity_lock_key("steamwrd")


def _taker_locks(taker):
    import asyncio
    import random
    db = _RecDb()
    ids = list(_MIXED)
    random.Random(7).shuffle(ids)
    asyncio.run(taker(db, ids))
    return [p["sid"] for s, p in db.calls if "pg_advisory_xact_lock" in s and "sid" in p]


def _takers():
    import match_hold
    return {
        "_ban_lock_and_gate": main._ban_lock_and_gate,
        "_identity_lock_many": main._identity_lock_many,
        "_guard_identities": match_hold._guard_identities,
    }


@pytest.mark.parametrize("name", ["_ban_lock_and_gate", "_identity_lock_many", "_guard_identities"])
def test_every_taker_of_several_identity_keys_takes_them_in_the_one_order(name):
    assert _taker_locks(_takers()[name]) == _MIXED_ORDER


def test_the_helper_takes_the_exclusive_keys_in_its_one_ordered_pass():
    import asyncio
    db = _RecDb()
    asyncio.run(main._ban_lock_and_gate(db, ["9000000000000016", "9000"], None,
                                         actor="steamwrd", exclusive=["9000000000000016"]))
    locks = [(p["sid"], "shared" in s) for s, p in db.calls if "pg_advisory_xact_lock" in s]
    assert locks == [("9000", True), ("steamwrd", True), ("9000000000000016", False)], locks


def test_mutant_the_report_window_guard_back_on_bare_sorted_takes_another_order():
    import inspect
    import textwrap
    import match_hold
    src = textwrap.dedent(inspect.getsource(match_hold._guard_identities))
    old = ", key=identity_lock_key)"
    assert src.count(old) == 1
    ns = dict(vars(match_hold))
    exec(compile(src.replace(old, ")"), "<mutant>", "exec"), ns)
    assert _taker_locks(ns["_guard_identities"]) != _MIXED_ORDER


def test_every_identity_key_taker_orders_by_the_one_key_or_is_listed():
    assert B.identity_lock_failures(_api_modules()) == []
    assert all(r for r in B.SINGLE_KEY_TAKERS.values())


def test_mutant_a_taker_back_on_bare_sorted_fails_the_identity_census():
    mods = _api_modules()
    old = "keys = sorted({str(s) for s in steam_ids if s is not None}, key=identity_lock_key)"
    assert mods["match_hold"].count(old) == 1
    mods["match_hold"] = mods["match_hold"].replace(
        old, "keys = sorted({str(s) for s in steam_ids if s is not None})")
    assert B.identity_lock_failures(mods) == [
        "match_hold._guard_identities: takes several identity keys and does not order by identity_lock_key"]


_PLANTED_KEYS = """
async def planted_one(db, sid):
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:sid))"), {"sid": sid})

async def planted_bare(db, name):
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": name})
"""


def test_negative_control_an_unlisted_single_taker_and_an_unprefixed_key_fail():
    mods = _api_modules()
    mods["main"] = mods["main"] + _PLANTED_KEYS
    assert B.identity_lock_failures(mods) == [
        "main.planted_one: takes one identity key and is not listed",
        "main.planted_bare: an advisory key that is neither the identity key nor prefixed"]
    bad = B.identity_lock_failures(_api_modules(), single={})
    assert {b.split(":")[0] for b in bad} == {f"{m}.{n}" for m, n in B.SINGLE_KEY_TAKERS}


def test_every_function_with_the_shared_read_and_an_exclusive_key_is_listed():
    assert B.shared_and_exclusive_failures(_api_modules()) == []
    assert all(r for r in B.SHARED_AND_EXCLUSIVE.values())


_PLANTED_UPGRADE = """
async def planted_upgrade(db, sid):
    await _ban_lock_and_gate(db, [sid])
    await _identity_lock_many(db, [sid])
"""


def test_mutant_a_shared_read_then_an_exclusive_key_fails_the_census():
    mods = _api_modules()
    mods["main"] = mods["main"] + _PLANTED_UPGRADE
    assert B.shared_and_exclusive_failures(mods) == [
        "main.planted_upgrade: reaches the shared read and an exclusive identity key, not listed"]
    bad = B.shared_and_exclusive_failures(_api_modules(), listed={})
    assert len(bad) == len(B.SHARED_AND_EXCLUSIVE), bad


# ---- F1 c: every call site of each mode's insert core reaches the writer's check

def test_every_insert_core_reads_the_ban_and_every_site_is_listed():
    bad = B.insert_core_failures(_api_modules())
    assert bad == [], "\n".join(bad)


def test_mutant_a_new_call_site_of_an_insert_core_fails_the_census():
    mods = _api_modules()
    mods["main"] += "\n\nasync def planted_replay(db, report):\n    return await _settle_ovt_report(db, report)\n"
    bad = B.insert_core_failures(mods)
    assert bad == ["('main', 'planted_replay', '_settle_ovt_report', 'call'): named 1 time(s), 0 listed"], bad


@pytest.mark.parametrize("core", sorted(B.INSERT_CORES))
def test_mutant_an_insert_core_without_the_writers_check_fails_the_census(core):
    mods = _api_modules()
    tree = ast.parse(mods["main"])
    for fn in B._functions(tree):
        if fn.name == core:
            for st in ast.walk(fn):
                if isinstance(st, ast.Call) and B._name_of(st) in B.LOCK_CALLERS:
                    st.func = ast.Name(id="_planted_noop", ctx=ast.Load())
    mods["main"] = ast.unparse(tree)
    bad = B.insert_core_failures(mods)
    assert any(b.startswith(f"main.{core}: the ") for b in bad), bad


# ---- F4: every BAN-class writer reads the ban under an identity lock ------

_F4_ROWS = None


def _f4_rows_and_funcs():
    global _F4_ROWS
    if _F4_ROWS is None:
        _F4_ROWS = _all_rows_and_funcs()
    return _F4_ROWS


def test_every_ban_class_writer_reads_the_ban_under_an_identity_lock_or_is_listed():
    rows, funcs = _f4_rows_and_funcs()
    bad = B.ban_writers_without_the_lock(rows, funcs)
    assert bad == [], "\n".join(bad)
    for key, why in B.F4_LISTED.items():
        assert why.strip(), key


def _with_unlocked_check(funcs, name):
    """funcs with main.<name>'s locking-helper calls turned into the plain
    check e0ef1492 had (_check_ban_or_raise): still BAN, no lock."""
    out = {m: dict(fs) for m, fs in funcs.items()}
    fn = copy.deepcopy(out["main"][name])
    n = 0
    for c in ast.walk(fn):
        if isinstance(c, ast.Call) and B._name_of(c) == "_ban_lock_and_gate":
            c.func = ast.Name(id="_check_ban_or_raise", ctx=ast.Load())
            n += 1
    assert n == 1, (name, n)
    out["main"][name] = fn
    return out


def test_mutant_a_bet_without_the_lock_fails_the_census():
    rows, funcs = _f4_rows_and_funcs()
    bad = B.ban_writers_without_the_lock(rows, _with_unlocked_check(funcs, "place_bet"))
    assert "POST /api/v1/bets: a BAN-class writer that reads the ban under no identity lock" in bad, bad
    assert all("bets: " in b for b in bad), bad   # the discord bet goes through place_bet


def test_negative_control_the_listed_writers_and_the_lockers_are_load_bearing():
    rows, funcs = _f4_rows_and_funcs()
    bad = B.ban_writers_without_the_lock(rows, funcs, listed={})
    assert len(bad) == len(B.F4_LISTED), bad
    bad = B.ban_writers_without_the_lock(rows, funcs, lockers={**B.IDENTITY_LOCKERS, "_planted_locker": "x"})
    assert bad == ["_planted_locker: listed as an identity locker and takes no identity lock"], bad
    lockers = dict(B.IDENTITY_LOCKERS)
    for k in [k for k in lockers if k.startswith("_pc_")]:
        lockers.pop(k)
    bad = B.ban_writers_without_the_lock(rows, funcs, lockers=lockers)
    assert bad and all("/pc/" in b for b in bad), bad


# ---- FIX-1B point 4: the second read in the LAST transaction ----------------

def test_every_multi_commit_ban_writer_reads_the_ban_in_its_last_transaction_or_is_listed():
    rows, funcs = _f4_rows_and_funcs()
    assert B.last_transaction_failures(rows, funcs) == []
    assert B.return_guard_failures(funcs) == []
    assert all(why.strip() for why in B.MULTI_COMMIT_LISTED.values())
    assert all(why.strip() for _k, why in B.RETURN_GUARDED.values())
    assert all(why.strip() for why in B.TRAILING_REMOVALS.values())


def _without_call(funcs, fn_name, callee):
    out = {m: dict(fs) for m, fs in funcs.items()}
    fn = copy.deepcopy(out["main"][fn_name])
    n = 0
    for c in ast.walk(fn):
        if isinstance(c, ast.Call) and B._name_of(c) == callee:
            c.func = ast.Name(id="_planted_no_read", ctx=ast.Load())
            n += 1
    assert n == 1, (fn_name, callee, n)
    out["main"][fn_name] = fn
    return out


def test_mutant_a_settle_without_its_second_read_fails_the_census():
    # the 1v2 report: the window receipt commits, then the settle's own
    # transaction reads the ban again under the guards; without that read
    # the last transaction reads nothing
    rows, funcs = _f4_rows_and_funcs()
    bad = B.last_transaction_failures(rows, _without_call(funcs, "_settle_ovt_report",
                                                          "_settle_writer_ban_check"))
    assert any(b.startswith("POST /api/v1/ovt/matches: a path commits twice") for b in bad), bad


def test_negative_control_the_listed_routes_and_the_guards_are_load_bearing():
    rows, funcs = _f4_rows_and_funcs()
    bad = B.last_transaction_failures(rows, funcs, listed={})
    assert sorted(b.split(":")[0] for b in bad) == sorted(f"{m} {p}" for m, p in B.MULTI_COMMIT_LISTED), bad
    bad = B.return_guard_failures(funcs, guarded={**B.RETURN_GUARDED, "_planted_helper": ("locked", "x")})
    assert bad == ["_planted_helper: listed in RETURN_GUARDED and never called"], bad


_PLANTED_TXN = """
async def planted_two(db, sid):
    await _ban_lock_and_gate(db, [sid])
    await db.execute(text("UPDATE players SET gold_earned = gold_earned + 1 WHERE steam_id = :s"), {"s": sid})
    await db.commit()
    await db.execute(text("UPDATE players SET gold_earned = gold_earned + 1 WHERE steam_id = :s"), {"s": sid})
    await db.commit()

async def planted_two_read(db, sid):
    await _ban_lock_and_gate(db, [sid])
    await db.execute(text("UPDATE players SET gold_earned = gold_earned + 1 WHERE steam_id = :s"), {"s": sid})
    await db.commit()
    await _ban_lock_and_gate(db, [sid])
    await db.execute(text("UPDATE players SET gold_earned = gold_earned + 1 WHERE steam_id = :s"), {"s": sid})
    await db.commit()

async def planted_quiet(db, sid, sp):
    await _ban_lock_and_gate(db, [sid])
    await db.commit()
    await db.execute(text("UPDATE players SET gold_earned = gold_earned + 1 WHERE steam_id = :s"), {"s": sid})
    await sp.commit()
    async with async_session() as other:
        await other.execute(text("DELETE FROM pc_jobs WHERE id = 1"))
        await other.commit()
    await db.commit()

async def planted_guarded(db, sid):
    await db.execute(text("UPDATE players SET seen = now() WHERE steam_id = :s"), {"s": sid})
    await db.commit()
    got = await _planted_snapshot(db, sid)
    if got is None:
        return None
    await db.execute(text("UPDATE players SET gold_earned = gold_earned + 1 WHERE steam_id = :s"), {"s": sid})
    await db.commit()

async def _planted_snapshot(db, sid):
    if sid:
        await db.rollback()
        return None
    await _ban_lock_and_gate(db, [sid])
    return 1
"""


def _planted_txn_funcs():
    tree = ast.parse(_PLANTED_TXN.replace("sp.commit", "sp_savepoint.commit"))
    return {"main": {n.name: n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)}}


def _ends_bad(funcs, name, guarded=None):
    saved = dict(B.RETURN_GUARDED)
    try:
        if guarded is not None:
            B.RETURN_GUARDED.clear()
            B.RETURN_GUARDED.update(guarded)
        ends = B.last_transaction_paths(funcs, "main", name)
    finally:
        B.RETURN_GUARDED.clear()
        B.RETURN_GUARDED.update(saved)
    return any(n >= 2 and p is False for n, _r, _w, p, _a in ends)


def test_the_walk_tells_a_second_read_a_savepoint_another_session_and_a_guarded_return():
    funcs = _planted_txn_funcs()
    assert _ends_bad(funcs, "planted_two")              # the mutant shape: no second read
    assert not _ends_bad(funcs, "planted_two_read")     # the second read in the last transaction
    assert not _ends_bad(funcs, "planted_quiet")        # empty commit, savepoint, own session
    assert _ends_bad(funcs, "planted_guarded", guarded={})
    assert not _ends_bad(funcs, "planted_guarded", guarded={"_planted_snapshot": ("locked", "x")})


# ---------------------------------------------------------------------------
# F2 b: the table census. Every table standing after the migrations is
# classed by name (ban_sweep_tables.TABLE_CLASSES), both ways, and every LIVE
# table is named by the void; the live census (test_ban_sweep_live_census_pg)
# proves each LIVE table's rows of a banned account end.
import glob as _glob  # noqa: E402

from ban_sweep_tables import TABLE_CLASSES  # noqa: E402

_SQL_DIR = os.path.normpath(os.path.join(HERE, "..", "sql"))


def _sql_files():
    out = {}
    for f in _glob.glob(os.path.join(_SQL_DIR, "*.sql")):
        with open(f, encoding="utf-8", errors="replace") as fh:
            out[os.path.basename(f)] = fh.read()
    return out


def _orm():
    with open(os.path.join(API, "models.py"), encoding="utf-8") as fh:
        return fh.read()


def _main_source():
    with open(os.path.join(API, "main.py"), encoding="utf-8") as fh:
        return fh.read()


def _void_text(src):
    tree = ast.parse(src)
    funcs = {"main": {n.name: n for n in tree.body
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}}
    return B.void_sql_text(funcs, module_source=src)


def test_every_standing_table_is_classed_and_every_classed_table_stands():
    standing = B.standing_tables(_sql_files(), _orm())
    assert len(standing) > 150, len(standing)
    assert B.table_class_failures(standing, TABLE_CLASSES) == []


def test_every_live_table_is_named_by_the_void():
    text, seen = _void_text(_main_source())
    assert "_apply_ban_core" in seen and "_ban_void_apply" in seen, sorted(seen)
    live = [t for t, (c, _w) in TABLE_CLASSES.items() if c == B.LIVE]
    assert len(live) >= 20, live
    assert B.void_coverage_failures(TABLE_CLASSES, text) == []


def test_the_standing_set_follows_creates_drops_renames_and_skips_temp_and_side_files():
    files = {
        "001_a.sql": "CREATE TABLE IF NOT EXISTS alpha (id int); CREATE TABLE beta (id int);"
                     " CREATE TEMP TABLE scratch (id int); -- CREATE TABLE commented (id int)",
        "002_b.sql": "DROP TABLE IF EXISTS beta; ALTER TABLE alpha RENAME TO gamma;",
        "rollback_002_b.sql": "CREATE TABLE rollback_only (id int);",
        "003_c.sql": "/* CREATE TABLE in_a_comment (id int) */ CREATE TABLE delta (id int);",
    }
    got = B.standing_tables(files, 'class X:\n    __tablename__ = "orm_only"\n')
    assert got == {"gamma", "delta", "orm_only"}, got


def test_mutant_a_planted_table_that_is_not_classed_fails_the_census():
    files = _sql_files()
    files["999_planted.sql"] = "CREATE TABLE IF NOT EXISTS planted_account_state (steam_id text);"
    fails = B.table_class_failures(B.standing_tables(files, _orm()), TABLE_CLASSES)
    assert fails == ["planted_account_state: stands after the migrations and is not classed"], fails
    files["999_planted.sql"] = "DROP TABLE IF EXISTS chat_mirrors;"
    fails = B.table_class_failures(B.standing_tables(files, _orm()), TABLE_CLASSES)
    assert fails == ["chat_mirrors: classed and does not stand"], fails


def test_mutant_a_live_table_left_out_of_the_void_fails_the_census():
    src = _main_source()
    stmt = '"DELETE FROM lfp_pings WHERE steam_id = :sid AND posted_at IS NULL"'
    assert src.count(stmt) == 1
    text, _seen = _void_text(src.replace(stmt, '"SELECT 1"'))
    assert B.void_coverage_failures(TABLE_CLASSES, text) == [
        "lfp_pings: a LIVE table the void never names"]
    classes = dict(TABLE_CLASSES, chat_mutes=(B.LIVE, "planted: a mute the ban must end"))
    text, _seen = _void_text(src)
    assert B.void_coverage_failures(classes, text) == ["chat_mutes: a LIVE table the void never names"]
