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
