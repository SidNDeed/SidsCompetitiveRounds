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


def _stub_names_patched_into_main(tree) -> set:
    out = set()
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "setattr" and len(n.args) >= 3
                and isinstance(n.args[0], ast.Name) and n.args[0].id == "main"
                and isinstance(n.args[1], ast.Constant)
                and n.args[1].value == "_check_steam_session"):
            v = n.args[2]
        elif (isinstance(n, ast.Assign) and len(n.targets) == 1
              and isinstance(n.targets[0], ast.Attribute)
              and n.targets[0].attr == "_check_steam_session"
              and isinstance(n.targets[0].value, ast.Name)
              and n.targets[0].value.id == "main"):
            v = n.value
        else:
            continue
        name = v.attr if isinstance(v, ast.Attribute) else getattr(v, "id", None)
        if name:
            out.add(name)
    return out


def _stubs_without_banned_ok(sources: dict) -> list:
    """(file, function) for every function defined in a file under the name
    that file patches in as main._check_steam_session, when it takes neither
    banned_ok nor **kwargs."""
    bad = []
    for fname, src in sorted(sources.items()):
        tree = ast.parse(src)
        names = _stub_names_patched_into_main(tree)
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names:
                a = n.args
                if a.kwarg is None and not any(x.arg == "banned_ok"
                                               for x in a.args + a.kwonlyargs):
                    bad.append((fname, n.name))
    return bad


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


def test_negative_control_a_stand_in_without_banned_ok_is_named():
    planted = {
        "planted_a.py": ("async def stub(request, steam_id, db):\n    return None\n"
                         "monkeypatch.setattr(main, '_check_steam_session', stub)\n"),
        "planted_b.py": ("async def stub2(request, steam_id, db, **_kw):\n    return None\n"
                         "main._check_steam_session = stub2\n"),
    }
    assert _stubs_without_banned_ok(planted) == [("planted_a.py", "stub")]
