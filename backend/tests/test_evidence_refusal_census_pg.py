"""The evidence refusal census (migration 414, evidence_refusal_daily), against
a real PostgreSQL (lane server-fix-1114, part B, fix 2).

The method (fix 2): the request path only NOTES. ONE counting place,
main.evidence_census_gate, notes every FINAL answer of 400..599 to a POST on
one of the four evidence paths in a bounded in-memory tally (_evc_settle and
_evc_note, plain functions), under the field the route left on request.state
(_evc_leave) or the gate_* field of the status. ONE janitor step,
_evc_flush_janitor_step in queue_cleanup_loop, writes the tally's deltas.

  P1  structure, by the parse tree of main.py as it is on disk: the note,
      the settle and the leave, and every main.py function they reach, are
      plain functions with no await, no output call (a called name holding
      `print`) and no name of a session, engine, connection, output stream,
      write, log, sleep, file or socket; the gate holds exactly one await
      (call_next); none of the four routes calls a census function but
      _evc_leave. One mutant each, and four in the helpers.
  P2  through the whole ASGI app, reading the TALLY: each place of the
      derivation table, a route refusal once, a refusal whose session
      cleanup then fails (500 with the route's field) once, an unhandled
      error, an accepted record, 405 and 404, the replica's 503. The request
      path touches no table and prints no census line.
  P3  the cap: at EVC_TALLY_MAX_KEYS keys a new key is dropped and counted,
      an existing key still counts; the dropped number is in the flush's
      line and is reset. The fill's size is this file's constant CAP, never
      the attribute a control patches.
  P4  the flush: deltas added, last_at never moves back, the tally empty
      afterwards; two flushes add; a failure before the commit merges back;
      a failure of the commit drops the batch and prints its size; the table
      absent: the step skips and keeps the tally; an empty tally executes
      nothing; the transaction's three settings are in effect.
  P5  the janitor: the live inventory has no dynamic site and holds the
      flush's statements by name; the real boot self-test, run against this
      database (414 applied), checks each of them with verdict explained (a
      data statement's ok) and fails nothing of the census's; the overall ok
      is the janitor file's full-schema test, since this case's schema lacks
      other janitor statements' objects; its
      control, the table gone: the flush's INSERT is reported failed with
      42P01 and janitor_selftest reads 0, and the flush step skips and keeps
      the tally. Every bind of every census statement is typed.
  P6  end to end once: a refused seat record through the stack, then one
      janitor step: the row is in evidence_refusal_daily with n = 1.
  B   the key's bounds: the version rule, the vocabulary, the 401 rule, the
      table's CHECKs, real records (stored, repeat, conflict, a made-up key).

No proof here depends on a wall-clock race: nothing on the request path
waits on anything. Every control runs one mutant and asserts the mutant's
OWN outcome (lesson 1187).

Built on seat_evidence_pg's case (every numbered migration replayed, so 414 is
in it) and the seat-evidence live helpers.
"""
import ast
import contextlib
import io
import json
import re
import types
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import HTTPException

import database  # noqa: E402
import main  # noqa: E402
import seat_evidence as se  # noqa: E402
import seat_evidence_fixtures as fx  # noqa: E402
import test_seat_evidence_live as sl  # noqa: E402
from test_seat_evidence_live import live, signing  # noqa: E402,F401  (fixtures)

CA, CB, CX = "1000000000000801", "1000000000000802", "1000000000000899"   # CX: never registered

# kind -> (route, module attribute in main, the module's function names, switch key)
_STD = {"setting": "setting", "env": "parse_envelope", "sig": "verify_sig",
        "rec": "parse_record", "store": "store_record"}
ROUTES = {
    "seat": ("submit_seat_evidence", "_sev", _STD, "seat_evidence_off"),
    "card": ("submit_card_evidence", "_cev", _STD, "card_evidence_off"),
    "combat": ("submit_combat_evidence", "_cbev", _STD, "combat_evidence_off"),
    "clock": ("submit_identity_clock_evidence", "_ice",
              {"setting": "ice_setting", "env": "ice_parse_envelope", "sig": "ice_verify_sig",
               "rec": "ice_parse_record", "store": "ice_store_record"},
              "identity_clock_evidence_off"),
}
REF = se.EvidenceRefused

# scenario -> (what the patched module does, expected (status, counted field) or None)
SCENARIOS = {
    "401": (None, (401, "seat_session")),
    "503": ({"setting": "0"}, (503, "<off>")),
    "400": ({"env": REF(400, "envelope_keys")}, (400, "envelope_keys")),
    "403": ({"sig": False}, (403, "signature")),
    "413": ({"rec": REF(413, "record_bytes")}, (413, "record_bytes")),
    "422": ({"rec": REF(422, "record")}, (422, "record")),
    "422_unlisted": ({"rec": REF(422, "zz_made_up_key_9")}, (422, "unlisted")),
    "409_not_ready": ({"other": CX}, (409, "not_ready")),
    "409_conflict": ({"store": REF(409, "conflict")}, (409, "conflict")),
    "429": ({"store": REF(429, "seat_hourly_cap")}, (429, "seat_hourly_cap")),
    "500": ({"store": RuntimeError("store failed")}, (500, "internal")),
    "stored": ({"store": {"status": "recorded"}}, None),
    "repeat": ({"store": {"status": "already_recorded"}}, None),
}
REFUSALS = sorted(n for n, (_p, want) in SCENARIOS.items() if want is not None)


@pytest.fixture(autouse=True)
def _fresh_tally(monkeypatch):
    """Every test starts on an empty tally, no dropped number and no cached
    table answer; the module's own state is put back afterwards."""
    monkeypatch.setattr(main, "_EVC_TALLY", {})
    monkeypatch.setattr(main, "_EVC_DROPPED", [0])
    monkeypatch.setattr(main, "_EVC_TABLE_FOUND", False)
    yield


def _tally():
    """The tally summed over its day: {(kind, status, field, version): n}."""
    out = {}
    for (_day, k, s, f, v), (n, _last) in main._EVC_TALLY.items():
        out[(k, s, f, v)] = out.get((k, s, f, v), 0) + n
    return out


def _census_lines(lines):
    return [ln for ln in lines if ln.startswith("[EVIDENCE-CENSUS]")]


async def _census(sm):
    rows = await sl._rows(sm, "SELECT kind, status, field, mod_version, n FROM evidence_refusal_daily")
    return {(r["kind"], r["status"], r["field"], r["mod_version"]): r["n"] for r in rows}


def _delta(before, after):
    return {k: after.get(k, 0) - before.get(k, 0) for k in set(before) | set(after)
            if after.get(k, 0) != before.get(k, 0)}


def _patch(monkeypatch, kind, plan):
    """The kind's module made to answer `plan` at its one step; every other
    step passes."""
    _route, attr, names, _off = ROUTES[kind]
    mod = getattr(main, attr)
    plan = dict(plan or {})
    other = plan.pop("other", CB)

    def ret(v):
        async def a(*_a, **_k):
            if isinstance(v, BaseException):
                raise v
            return v

        def s(*_a, **_k):
            if isinstance(v, BaseException):
                raise v
            return v
        return a, s

    async_steps = {"setting", "store"}
    defaults = {"setting": "1", "env": {"seat": CA, "other": other, "stable": "census_k"},
                "sig": True, "rec": {}, "store": {"status": "recorded"}}
    for step, fn_name in names.items():
        v = plan.get(step, defaults[step])
        a, s = ret(v)
        monkeypatch.setattr(mod, fn_name, a if step in async_steps else s)
    if kind == "clock":
        monkeypatch.setattr(main._ice, "ice_parse_clock", lambda *a, **k: None)
        monkeypatch.setattr(main._conn_ranges, "classify_address", lambda addr: ("unknown", "u"))


# -- the whole app -------------------------------------------------------------

@contextlib.asynccontextmanager
async def _app(live, monkeypatch, get_db=None):
    """The whole ASGI app (every middleware and exception handler), its
    database the case's."""
    async def _db():
        async with live.sm() as s:
            yield s
    monkeypatch.setitem(main.app.dependency_overrides, main.get_db, get_db or _db)
    monkeypatch.setattr(main, "_RL_BUCKETS", main._rl_defaultdict(main._rl_deque))
    transport = httpx.ASGITransport(app=main.app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://evc.test") as client:
        yield client


async def _through_app(live, monkeypatch, kind="seat", plan=None, version="1.41.0", method="POST",
                       path=None, setup=None, get_db=None, token=True, body=None, patch=True):
    """One request through the whole app: its status and body, the TALLY's
    change, the table's change (the request path must touch none), and the
    census lines printed while it ran (the request path must print none)."""
    await sl._players(live.sm, CA, CB)
    tok = await sl._session(live.sm, CA) if token else None
    if patch:
        _patch(monkeypatch, kind, plan if plan is not None else {"sig": False})
    if setup is not None:
        setup()
    headers = {}
    if tok:
        headers["X-Session-Token"] = tok
    if version is not None:
        headers["X-Mod-Version"] = version
    path = path or main._EVC_KINDS[kind][1]
    before, rows_before = _tally(), await _census(live.sm)
    buf = io.StringIO()
    async with _app(live, monkeypatch, get_db) as client:
        with contextlib.redirect_stdout(buf):
            r = await client.request(method, path, json=body if body is not None else {"seat_steam_id": CA},
                                     headers=headers)
    try:
        answer = r.json()
    except Exception:  # noqa: BLE001 -- a plain-text 500
        answer = r.text
    return {"status": r.status_code, "body": answer, "delta": _delta(before, _tally()),
            "rows": _delta(rows_before, await _census(live.sm)),
            "lines": _census_lines(buf.getvalue().splitlines())}


def _once(out, key):
    """Counted exactly once under `key`, nothing else; no table work and no
    census line on the request path."""
    assert out["delta"] == {key: 1}, out
    assert out["rows"] == {} and out["lines"] == [], out


# -- P1: structure ---------------------------------------------------------------

# A name (a variable, a called name or an attribute) whose presence means I/O:
# a session, engine, connection or bind; an output stream, a write, a flush or
# a log; a blocking sleep; a file, a socket, a process or a URL. An output
# CALL is also any called name holding `print` (print, _janitor_print).
_NO_IO_NAME = re.compile(r"session|engine|connect|bind|^db$|stdout|stderr|^write$|^writelines$"
                         r"|^flush$|logg|sleep|^open$|socket|subprocess|urlopen")
PLAIN = ("_evc_note", "_evc_settle", "_evc_leave")
# Every main.py function the request path's census reaches from PLAIN (the
# note, the settle, the leave and their helpers): pinned, so a new helper is
# read by test_p1_everything_the_request_path_reaches_is_plain before it passes.
REQUEST_PATH = {"_evc_answer_field", "_evc_field", "_evc_key", "_evc_leave", "_evc_note",
                "_evc_settle", "_evc_version", "_parse_pure_dotted_version"}


def _main_source():
    with open(main.__file__, encoding="utf-8") as fh:
        return fh.read()


def _function(tree, name):
    (f,) = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == name]
    return f


def _sources(*names):
    """main's top-level functions `names`, as main.py reads on disk NOW, taken
    by the parse tree. Not inspect.getsource: it takes the line number from
    the import and the text from the file, so a main.py edited after the
    import returns another block of lines."""
    src = _main_source()
    tree = ast.parse(src)
    return {name: ast.get_source_segment(src, _function(tree, name)) for name in names}


def _plain_violations(tree, name):
    """What makes `name` other than a plain, I/O-free function."""
    f = _function(tree, name)
    out = []
    if isinstance(f, ast.AsyncFunctionDef):
        out.append((name, "coroutine"))
    for n in ast.walk(f):
        if isinstance(n, ast.Await):
            out.append((name, "await"))
        if isinstance(n, ast.Call):
            called = n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
            if "print" in called:
                out.append((name, "print"))
        ident = n.id if isinstance(n, ast.Name) else n.attr if isinstance(n, ast.Attribute) else None
        if ident and _NO_IO_NAME.search(ident):
            out.append((name, "name " + ident))
    return out


def _reached(tree, roots):
    """The top-level functions of main.py that `roots` reach by naming them
    (a call, or the function passed as a value), the roots included. The
    walk visits each function once, so it ends."""
    defs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    seen, todo = set(), list(roots)
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        for n in ast.walk(defs[name]):
            if isinstance(n, ast.Name) and n.id in defs and n.id not in seen:
                todo.append(n.id)
    return seen


def _reached_violations(src):
    tree = ast.parse(src)
    return sorted(v for name in _reached(tree, PLAIN) for v in _plain_violations(tree, name))


def _route_names():
    names = {}
    for kind, (_m, path, _x) in main._EVC_KINDS.items():
        (hit,) = [r for r in main.app.routes if getattr(r, "path", None) == path
                  and "POST" in getattr(r, "methods", ())]
        names[kind] = hit.endpoint.__name__
    return names


def _census_calls(tree, name):
    """Every census function `name` calls (a name starting _evc or naming
    the census), and whether any of them is awaited."""
    f = _function(tree, name)
    called, awaited = set(), False
    for n in ast.walk(f):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and (
                n.func.id.startswith("_evc") or "census" in n.func.id):
            called.add(n.func.id)
        if isinstance(n, ast.Await) and isinstance(n.value, ast.Call) and isinstance(
                n.value.func, ast.Name) and n.value.func.id.startswith("_evc"):
            awaited = True
    return called, awaited


def _gate_awaits(tree):
    f = _function(tree, "evidence_census_gate")
    return [ast.unparse(n.value) for n in ast.walk(f) if isinstance(n, ast.Await)]


def test_p1_the_note_the_settle_and_the_leave_are_plain_functions():
    tree = ast.parse(_main_source())
    for name in PLAIN:
        assert _plain_violations(tree, name) == [], name


def test_p1_the_gate_awaits_call_next_only_and_counts_by_the_settle():
    tree = ast.parse(_main_source())
    assert _gate_awaits(tree) == ["call_next(request)"]
    assert _census_calls(tree, "evidence_census_gate") == ({"_evc_settle"}, False)
    assert _plain_violations(tree, "evidence_census_gate").count(
        ("evidence_census_gate", "print")) == 0


def test_p1_the_routes_only_leave_the_field():
    tree = ast.parse(_main_source())
    names = _route_names()
    assert sorted(names) == sorted(ROUTES) and all(names[k] == ROUTES[k][0] for k in ROUTES)
    for kind, name in names.items():
        assert _census_calls(tree, name) == ({"_evc_leave"}, False), (kind, name)


def test_p1_control_an_await_in_the_note():
    src = _main_source()
    old = "def _evc_note(kind, status, field, version) -> None:"
    assert src.count(old) == 1
    src = src.replace(old, "async def _evc_note(kind, status, field, version) -> None:")
    old2 = "        now = datetime.now(timezone.utc)\n        key = (now.date(), kind, status, field, version)"
    assert src.count(old2) == 1
    src = src.replace(old2, "        await asyncio.sleep(0)\n" + old2)
    assert _plain_violations(ast.parse(src), "_evc_note") == [
        ("_evc_note", "coroutine"), ("_evc_note", "await"), ("_evc_note", "name sleep")]


def test_p1_control_a_print_in_the_note():
    src = _main_source()
    old2 = "        now = datetime.now(timezone.utc)\n        key = (now.date(), kind, status, field, version)"
    assert src.count(old2) == 1
    src = src.replace(old2, "        print('evc_probe_print')\n" + old2)
    assert _plain_violations(ast.parse(src), "_evc_note") == [("_evc_note", "print")]


def test_p1_control_a_route_that_counts_by_itself():
    src = _main_source()
    old = ('        return _evc_leave(request, JSONResponse(status_code=401, '
           'content={"detail": "seat_session"}))')
    assert src.count(old) == 4
    i = src.index(old)                                   # the first: submit_seat_evidence
    src = src[:i] + '        _evc_note("seat", 401, "seat_session", "other")\n' + src[i:]
    tree = ast.parse(src)
    assert _census_calls(tree, "submit_seat_evidence") == ({"_evc_leave", "_evc_note"}, False)
    assert _census_calls(tree, "submit_card_evidence") == ({"_evc_leave"}, False)


def test_p1_everything_the_request_path_reaches_is_plain():
    """The note, the settle and the leave, and every main.py function they
    reach: no coroutine, no await, no output call, no I/O name."""
    src = _main_source()
    tree = ast.parse(src)
    reached = _reached(tree, PLAIN)
    assert reached == REQUEST_PATH, sorted(reached ^ REQUEST_PATH)
    assert _reached_violations(src) == []


_FIELD_BODY = '    return field if isinstance(field, str) and field in _EVC_FIELDS else "unlisted"\n'
_KEY_DOC_END = '    nothing it sent may vary its row: fixed field, version `other`."""\n'
_VERSION_TEST = "    if not _EVC_VERSION_RE.fullmatch(v):\n"
_NOTE_FIRST = ("        now = datetime.now(timezone.utc)\n"
               "        key = (now.date(), kind, status, field, version)\n")


def _mutate(src, anchor, before):
    assert src.count(anchor) == 1, anchor
    return src.replace(anchor, before + anchor)


def test_p1_control_a_new_helper_of_the_note_that_prints():
    src = _mutate(_main_source(), _NOTE_FIRST, "        _evc_probe_helper()\n")
    src += "\n\ndef _evc_probe_helper():\n    print('evc_probe_print')\n"
    assert _reached(ast.parse(src), PLAIN) == REQUEST_PATH | {"_evc_probe_helper"}
    assert _reached_violations(src) == [("_evc_probe_helper", "print")]


def test_p1_control_output_by_another_name_in_a_helper():
    src = _mutate(_main_source(), _FIELD_BODY, "    _sys.stdout.write('evc_probe')\n")
    assert _reached_violations(src) == [("_evc_field", "name stdout"), ("_evc_field", "name write")]


def test_p1_control_an_engine_through_an_attribute_in_a_helper():
    src = _mutate(_main_source(), _VERSION_TEST,
                  "    _evc_probe = getattr(request, 'app', None) and request.app.state.engine\n")
    assert _reached_violations(src) == [("_evc_version", "name engine")]


def test_p1_control_a_blocking_sleep_in_a_helper_of_the_settle():
    src = _mutate(_main_source(), _KEY_DOC_END, "")
    src = src.replace(_KEY_DOC_END, _KEY_DOC_END + "    _time.sleep(0)\n")
    assert _reached_violations(src) == [("_evc_key", "name sleep")]


# -- P2: through the app, reading the tally ----------------------------------------

# The places that can decide an answer to a POST on an evidence path, derived
# from the app (outermost first), each with what it can answer there and the
# test that drives it. A layer added or removed fails the derivation test.
MIDDLEWARE = [
    ("evidence_key_gate", "answers only under /api/v1/internal/evidence-report/: none here"),
    ("replica_write_gate", "503 read_replica, only on a read replica: not counted (ruling)"),
    ("evidence_census_gate", "the one counting place itself"),
    ("version_gate", "426 outdated: test_p2_version_gate_426"),
    ("maintenance_gate", "503 maintenance: test_p2_maintenance_gate_503"),
    ("rate_limit_gate", "413 payload_too_large, 429 rate_limited: test_p2_rate_limit_gate_*"),
    ("read_gate_cache_control", "never answers (adds a header to GET reads)"),
    ("CORSMiddleware", "answers only an OPTIONS preflight: not a POST"),
]
EXCEPTION_HANDLERS = [
    ("FfaReportRefusal", "raised only by the FFA report route: none here"),
    ("HTTPException", "a raised HTTPException's own status: test_p2_a_raised_http_exception"),
    ("RequestValidationError", "the four routes take no validated parameter: none here"),
    ("WebSocketRequestValidationError", "websocket only: none here"),
]
# Outside every handler: Starlette's ServerErrorMiddleware turns an error no
# handler took into a 500 (test_p2_an_unhandled_error_*, test_p2_the_framework_*).


def _layer_name(m):
    dispatch = (m.kwargs or {}).get("dispatch")
    return dispatch.__name__ if dispatch is not None else m.cls.__name__


def test_p2_the_places_that_can_answer_an_evidence_post_are_the_ones_classified(live):
    assert [_layer_name(m) for m in main.app.user_middleware] == [n for n, _w in MIDDLEWARE]
    assert sorted(getattr(k, "__name__", str(k)) for k in main.app.exception_handlers) == sorted(
        n for n, _w in EXCEPTION_HANDLERS)
    for kind in ROUTES:                                  # no validated parameter on the routes
        hit = next(r for r in main.app.routes if getattr(r, "path", None) == main._EVC_KINDS[kind][1])
        params = hit.dependant.query_params + hit.dependant.header_params + hit.dependant.body_params
        assert params == [], (kind, params)


def _b1_expected(kind, name):
    _plan, want = SCENARIOS[name]
    if want is None:
        return None
    status, field = want
    if field == "<off>":
        field = ROUTES[kind][3]
    version = "other" if status == 401 else "1.41.0"
    return (kind, status, field, version)


@pytest.mark.parametrize("name", sorted(SCENARIOS))
@pytest.mark.parametrize("kind", sorted(ROUTES))
def test_p2_each_route_refusal_is_counted_once_and_a_stored_record_never(live, monkeypatch, kind, name):
    plan, _want = SCENARIOS[name]
    out = live.run(_through_app(live, monkeypatch, kind=kind, plan=plan or {}, token=name != "401"))
    key = _b1_expected(kind, name)
    if key is None:
        assert out["status"] == 200 and out["delta"] == {} and out["rows"] == {}, (kind, name, out)
        return
    assert out["status"] == key[1], (kind, name, out)
    if name == "422_unlisted":                                     # the answer still names it
        assert out["body"] == {"detail": "zz_made_up_key_9"}, out
    _once(out, key)


@pytest.mark.parametrize("kind", sorted(ROUTES))
def test_p2_version_gate_426(live, monkeypatch, kind):
    out = live.run(_through_app(live, monkeypatch, kind=kind, version="1.0.0"))
    assert out["status"] == 426, out
    _once(out, (kind, 426, "gate_version", "other"))


def test_p2_version_gate_426_without_a_header(live, monkeypatch):
    out = live.run(_through_app(live, monkeypatch, version=None))
    assert out["status"] == 426, out
    _once(out, ("seat", 426, "gate_version", "other"))


def test_p2_maintenance_gate_503(live, monkeypatch):
    out = live.run(_through_app(live, monkeypatch,
                                setup=lambda: monkeypatch.setattr(main, "_in_maintenance", True)))
    assert out["status"] == 503, out
    _once(out, ("seat", 503, "gate_other", "1.41.0"))


def test_p2_rate_limit_gate_413(live, monkeypatch):
    out = live.run(_through_app(live, monkeypatch,
                                setup=lambda: monkeypatch.setattr(main, "_RL_MAX_BODY", 8)))
    assert out["status"] == 413, out
    _once(out, ("seat", 413, "gate_size", "1.41.0"))


def test_p2_rate_limit_gate_429(live, monkeypatch):
    def setup():
        monkeypatch.setattr(main, "_RL_GLOBAL", (0, 10.0))
        monkeypatch.setattr(main, "_RL_SENSITIVE", (0, 10.0))
    out = live.run(_through_app(live, monkeypatch, setup=setup))
    assert out["status"] == 429, out
    _once(out, ("seat", 429, "gate_rate", "1.41.0"))


def test_p2_a_raised_http_exception(live, monkeypatch):
    out = live.run(_through_app(live, monkeypatch,
                                plan={"setting": HTTPException(status_code=409, detail="probe")}))
    assert out["status"] == 409 and out["body"] == {"detail": "probe"}, out
    _once(out, ("seat", 409, "gate_other", "1.41.0"))


def test_p2_an_unhandled_error_before_the_route_leaves_a_field(live, monkeypatch):
    async def boom(_request):
        raise RuntimeError("probe: before the route's try")
    out = live.run(_through_app(live, monkeypatch,
                                setup=lambda: monkeypatch.setattr(main, "_sev_claimed_seat", boom)))
    assert out["status"] == 500, out
    _once(out, ("seat", 500, "gate_other", "1.41.0"))


def test_p2_the_framework_failing_a_dependency(live, monkeypatch):
    async def no_db():
        raise RuntimeError("probe: no database session")
        yield  # noqa: unreachable -- a generator dependency
    out = live.run(_through_app(live, monkeypatch, get_db=no_db))
    assert out["status"] == 500, out
    _once(out, ("seat", 500, "gate_other", "1.41.0"))


def test_p2_a_route_refusal_is_counted_once_with_its_field(live, monkeypatch):
    out = live.run(_through_app(live, monkeypatch))
    assert out["status"] == 403 and out["body"] == {"detail": "signature"}, out
    _once(out, ("seat", 403, "signature", "1.41.0"))


def test_p2_a_route_500_is_counted_once_with_its_field(live, monkeypatch):
    out = live.run(_through_app(live, monkeypatch, plan={"store": RuntimeError("probe")}))
    assert out["status"] == 500, out
    _once(out, ("seat", 500, "internal", "1.41.0"))


def test_p2_a_refusal_whose_session_cleanup_fails_is_counted_once_as_500(live, monkeypatch):
    """The route decides 403 and leaves `signature`; the request session's
    cleanup then raises, so the FINAL answer is 500: counted once, as 500,
    with the route's field."""
    async def failing_cleanup():
        async with live.sm() as s:
            yield s
        raise RuntimeError("probe: the session's cleanup failed")
    out = live.run(_through_app(live, monkeypatch, get_db=failing_cleanup))
    assert out["status"] == 500, out
    _once(out, ("seat", 500, "signature", "1.41.0"))


def test_p2_control_an_accepted_record_counts_nothing(live, monkeypatch):
    out = live.run(_through_app(live, monkeypatch, plan={}))
    assert out["status"] == 200 and out["delta"] == {} and out["rows"] == {}, out


def test_p2_a_wrong_method_and_an_unknown_path_are_not_evidence_refusals(live, monkeypatch):
    wrong = live.run(_through_app(live, monkeypatch, method="GET"))
    unknown = live.run(_through_app(live, monkeypatch, path="/api/v1/matches/seat-evidence-x"))
    assert (wrong["status"], wrong["delta"]) == (405, {}), wrong
    assert (unknown["status"], unknown["delta"]) == (404, {}), unknown


def test_p2_a_replica_refusal_is_not_counted(live, monkeypatch):
    """replica_write_gate is outside the census (ruling): on a read replica
    nothing is noted, and no janitor runs there to write."""
    out = live.run(_through_app(live, monkeypatch,
                                setup=lambda: monkeypatch.setattr(main, "IS_REPLICA", True)))
    assert out["status"] == 503 and out["delta"] == {}, out


def test_p2_a_failing_note_leaves_the_answer_unchanged(live, monkeypatch):
    planted = []

    def _raising_note(*_a):
        planted.append("evc_probe_note_fails")
        raise RuntimeError("evc_probe_note_fails")
    monkeypatch.setattr(main, "_evc_note", _raising_note)
    out = live.run(_through_app(live, monkeypatch))
    assert planted == ["evc_probe_note_fails"], planted               # it did raise, once
    assert out["status"] == 403 and out["body"] == {"detail": "signature"}, out
    assert out["delta"] == {} and out["lines"] == [], out


# -- B: the key's bounds -------------------------------------------------------------

def _req(version, field=None):
    state = types.SimpleNamespace()
    if field is not None:
        state.evc_field = field
    return types.SimpleNamespace(headers={"X-Mod-Version": version} if version is not None else {},
                                 state=state)


VERSIONS = [("1.41.0", "1.41.0"), (main.MIN_MOD_VERSION_EFFECTIVE, main.MIN_MOD_VERSION_EFFECTIVE),
            ("9.9.9", "other"), ("1.41.1", "other"), ("01.41.0", "other"), ("1.41.0x", "other"),
            ("1.41", "other"), ("", "other"), ("1.0.0", "other")]


@pytest.mark.parametrize("sent,stored", VERSIONS)
def test_b3_the_version_header_is_kept_only_inside_the_release_range(sent, stored):
    main._evc_settle(_req(sent, "signature"), "card", 403)
    assert _tally() == {("card", 403, "signature", stored): 1}, sent


def _two_401s():
    main._evc_settle(_req("1.41.0", "seat_session"), "seat", 401)
    main._evc_settle(_req("7.7.7", "zz_client_word"), "seat", 401)
    return _tally()


def test_b3_a_401_cannot_make_a_second_row_by_what_it_sends():
    assert _two_401s() == {("seat", 401, "seat_session", "other"): 2}


def test_b3_the_status_range_and_the_kind_are_closed():
    for status in (399, 200, 600):
        main._evc_settle(_req("1.41.0", "signature"), "seat", status)
    main._evc_settle(_req("1.41.0", "signature"), "fifth", 403)
    main._evc_settle(_req("1.41.0", "signature"), "seat", 599)
    main._evc_settle(_req("1.41.0", "signature"), "seat", 400)
    assert _tally() == {("seat", 599, "signature", "1.41.0"): 1, ("seat", 400, "signature", "1.41.0"): 1}


def test_b4_the_leave_validates_its_field_and_never_changes_the_answer():
    answer = main.JSONResponse(status_code=422, content={"detail": "zz_made_up_key_9"})
    r = _req("1.41.0")
    assert main._evc_leave(r, answer) is answer and r.state.evc_field == "unlisted"
    r2 = _req("1.41.0")
    assert main._evc_leave(r2, field="internal") is None and r2.state.evc_field == "internal"
    no_state = types.SimpleNamespace(headers={})                 # a request with no state
    assert main._evc_leave(no_state, answer) is answer


def test_b2_seat_real_records_stored_repeat_conflict_and_a_made_up_key(live, monkeypatch, signing):
    key = "ranked_sevcen_000001"
    first = sl._body(CA, CB, key)
    rec = dict(fx.base_record())
    rec["zz_extra_key"] = 1
    bad = fx.envelope(rec, seat=CA, other=CB, stable="ranked_sevcen_000002",
                      text=json.dumps(rec, separators=(",", ":")))
    out = [live.run(_through_app(live, monkeypatch, body=b, patch=False))
           for b in (first, first, sl._body(CA, CB, key, t0=12345), bad)]
    assert (out[0]["status"], out[0]["body"], out[0]["delta"]) == (200, {"status": "recorded"}, {}), out[0]
    assert (out[1]["status"], out[1]["body"], out[1]["delta"]) == (
        200, {"status": "already_recorded"}, {}), out[1]
    assert (out[2]["status"], out[2]["body"]) == (409, {"status": "conflict"}), out[2]
    _once(out[2], ("seat", 409, "conflict", "1.41.0"))
    assert (out[3]["status"], out[3]["body"]) == (422, {"detail": "zz_extra_key"}), out[3]
    _once(out[3], ("seat", 422, "unlisted", "1.41.0"))


@pytest.mark.parametrize("col,value", [("kind", "Seat"), ("status", 399), ("status", 600),
                                       ("field", "A b"), ("field", "x" * 49),
                                       ("mod_version", "1.41.0.1"), ("mod_version", "100.0.0"),
                                       ("n", 0)])
def test_b5_each_column_check_refuses_a_value_outside_its_bound(live, col, value):
    import asyncpg
    row = {"kind": "seat", "status": 422, "field": "record", "mod_version": "other", "n": 1}
    row[col] = value

    async def go():
        conn = await sl.sp.harness.connect_bound(sl.sp.DSN, live.case.schema)
        try:
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "INSERT INTO evidence_refusal_daily (day, kind, status, field, mod_version, n, "
                    "last_at) VALUES (current_date - 400, $1, $2, $3, $4, $5, now())",
                    row["kind"], row["status"], row["field"], row["mod_version"], row["n"])
            # the bounds themselves are admitted (a positive control on the same insert)
            for status, field in ((400, "gate_other"), (599, "gate_version"), (426, "gate_size")):
                await conn.execute(
                    "INSERT INTO evidence_refusal_daily (day, kind, status, field, mod_version, n, "
                    "last_at) VALUES (current_date - 401, 'seat', $1, $2, 'other', 1, now()) "
                    "ON CONFLICT DO NOTHING", status, field)
        finally:
            await conn.close()
    live.run(go())


def test_b5_every_literal_refusal_field_of_the_four_modules_is_in_the_vocabulary():
    """The closed vocabulary covers every field the server authors as a
    literal (so `unlisted` is only ever a client-sent name or a composite this
    list misses, never a plain literal), the composed names, and the gate_*
    set."""
    mods = {}
    for m, _path, parsers in main._EVC_KINDS.values():
        for x in (m, *parsers):
            mods[id(x)] = x
    seen = set()
    for mod in mods.values():
        tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", ""))
                    in ("EvidenceRefused", "Refusal") and len(n.args) >= 2
                    and isinstance(n.args[1], ast.Constant)):
                seen.add(n.args[1].value)
    assert seen and seen <= main._EVC_FIELDS, sorted(seen - main._EVC_FIELDS)
    assert {"hit_sent.reset_keyed_since", "ldir.plugins", "seat_session"} <= main._EVC_FIELDS
    gate = set(main._EVC_GATE_FIELDS.values()) | {main._EVC_GATE_OTHER}
    assert gate == {"gate_size", "gate_version", "gate_rate", "gate_other"}
    assert gate <= main._EVC_FIELDS
    assert all(main._EVC_FIELD_RE.fullmatch(w) for w in gate)
    assert "zz_made_up_key_9" not in main._EVC_FIELDS


def test_b5_the_four_routes_write_only_through_their_store():
    sources = _sources(*(r[0] for r in ROUTES.values()))
    for kind, (route, _attr, _n, _o) in ROUTES.items():
        src = sources[route]
        assert "INSERT" not in src and "UPDATE" not in src and "db.add" not in src, route
        assert src.count("return _evc_leave(request, ") == 5, route
        assert src.count('_evc_leave(request, field="internal")') == 1, route
        assert src.count("except HTTPException:") == 1, route
    assert main._EVC_FLUSH_SQL.count("INSERT INTO evidence_refusal_daily ") == 1


def test_b5_each_kind_names_its_route_by_path():
    """_EVC_KINDS is the one line per kind: its module, the POST path of its
    route (which the gate reads) and the modules it parses with."""
    for kind, (route, attr, _n, _o) in ROUTES.items():
        mod, path, parsers = main._EVC_KINDS[kind]
        assert mod is getattr(main, attr), kind
        assert parsers and all(isinstance(p, type(mod)) for p in parsers), kind
        hits = [r for r in main.app.routes if getattr(r, "path", None) == path
                and "POST" in getattr(r, "methods", ())]
        assert len(hits) == 1 and hits[0].endpoint is getattr(main, route), (kind, path)
    assert sorted(main._EVC_PATH_KINDS.values()) == sorted(ROUTES)


# -- P3: the cap ----------------------------------------------------------------------

# The production cap, restated as this file's constant. _fill_to_the_cap's
# loop is bounded by CAP, never by main.EVC_TALLY_MAX_KEYS: a control patches
# that attribute, and no loop or allocation here takes its size from a value a
# test patches. test_p3_the_cap_* asserts CAP == main.EVC_TALLY_MAX_KEYS.
CAP = 512


def _fill_to_the_cap():
    """CAP distinct keys, then a new key past the cap and an existing key."""
    for i in range(CAP):
        main._evc_note("seat", 422, "probe_%d" % i, "other")
    main._evc_note("seat", 422, "probe_new", "other")              # a new key past the cap
    main._evc_note("seat", 422, "probe_0", "other")                # an existing key
    return len(main._EVC_TALLY), main._EVC_DROPPED[0], _tally()


@contextlib.contextmanager
def _janitor_on(live, monkeypatch):
    """The janitor's session factory pointed at the case database."""
    monkeypatch.setattr(database, "async_session", live.sm)
    yield


async def _flush_lines():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await main._evc_flush_janitor_step()
    return _census_lines(buf.getvalue().splitlines())


def test_p3_the_cap_drops_a_new_key_counts_an_existing_one_and_reports_once(live, monkeypatch):
    assert main.EVC_TALLY_MAX_KEYS == CAP == 512
    n_keys, dropped, tally = _fill_to_the_cap()
    assert (n_keys, dropped) == (CAP, 1)
    assert tally[("seat", 422, "probe_0", "other")] == 2
    assert ("seat", 422, "probe_new", "other") not in tally
    with _janitor_on(live, monkeypatch):
        before = live.run(_census(live.sm))
        lines = live.run(_flush_lines())
        delta = _delta(before, live.run(_census(live.sm)))
    assert lines == ["[EVIDENCE-CENSUS] flushed 513 increment(s) in 512 key(s); 1 dropped by the cap"]
    assert len(delta) == 512 and delta[("seat", 422, "probe_0", "other")] == 2
    assert main._EVC_DROPPED == [0] and main._EVC_TALLY == {}


def test_p3_control_the_cap_one_higher_nothing_is_dropped(monkeypatch):
    """The cap lifted by one, the smallest lift that shows the difference: the
    key past the production cap is kept and nothing is dropped. The fill
    stays CAP + 2 notes."""
    monkeypatch.setattr(main, "EVC_TALLY_MAX_KEYS", CAP + 1)
    n_keys, dropped, tally = _fill_to_the_cap()
    assert (n_keys, dropped) == (CAP + 1, 0)
    assert tally[("seat", 422, "probe_new", "other")] == 1


# -- P4: the flush -------------------------------------------------------------------

_FUTURE_ROW = ("INSERT INTO evidence_refusal_daily (day, kind, status, field, mod_version, n, last_at) "
               "VALUES (CAST(timezone('UTC', now()) AS date), 'seat', 403, 'signature', '1.41.0', 5, "
               "now() + interval '1 day')")


async def _row(sm, field="signature"):
    rows = await sl._rows(sm, "SELECT n, last_at, last_at > now() AS future FROM evidence_refusal_daily "
                              "WHERE day = CAST(timezone('UTC', now()) AS date) AND kind = 'seat' "
                              "AND status = 403 AND field = :f AND mod_version = '1.41.0'", f=field)
    return dict(rows[0]) if rows else None


async def _exec(live, sql):
    conn = await sl.sp.harness.connect_bound(sl.sp.DSN, live.case.schema)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


async def _added_to_an_existing_row(live):
    await _exec(live, "DELETE FROM evidence_refusal_daily WHERE field IN ('signature', 'record')")
    await _exec(live, _FUTURE_ROW)
    for _ in range(2):
        main._evc_note("seat", 403, "signature", "1.41.0")
    main._evc_note("seat", 403, "record", "1.41.0")
    lines = await _flush_lines()
    return lines, await _row(live.sm), await _row(live.sm, "record")


def test_p4_deltas_are_added_and_last_at_never_moves_back(live, monkeypatch):
    with _janitor_on(live, monkeypatch):
        lines, row, new = live.run(_added_to_an_existing_row(live))
    assert lines == ["[EVIDENCE-CENSUS] flushed 3 increment(s) in 2 key(s); 0 dropped by the cap"]
    assert row["n"] == 7 and row["future"] is True, row           # 5 + 2; the later last_at kept
    assert new["n"] == 1 and new["future"] is False, new
    assert main._EVC_TALLY == {}


def test_p4_control_without_greatest_last_at_moves_back(live, monkeypatch):
    monkeypatch.setattr(main, "_EVC_FLUSH_SQL", main._EVC_FLUSH_SQL.replace(
        "GREATEST(evidence_refusal_daily.last_at, EXCLUDED.last_at)", "EXCLUDED.last_at"))
    with _janitor_on(live, monkeypatch):
        _lines, row, _new = live.run(_added_to_an_existing_row(live))
    assert row["n"] == 7 and row["future"] is False, row


async def _two_flushes(live):
    await _exec(live, "DELETE FROM evidence_refusal_daily WHERE field = 'signature'")
    out = []
    for _ in range(2):
        main._evc_note("seat", 403, "signature", "1.41.0")
        out.append(await _flush_lines())
    return out, await _row(live.sm)


def test_p4_two_flushes_of_one_key_add(live, monkeypatch):
    with _janitor_on(live, monkeypatch):
        lines, row = live.run(_two_flushes(live))
    assert lines == [["[EVIDENCE-CENSUS] flushed 1 increment(s) in 1 key(s); 0 dropped by the cap"]] * 2
    assert row["n"] == 2, row


def _two_notes():
    main._evc_note("seat", 403, "signature", "1.41.0")
    main._evc_note("seat", 403, "signature", "1.41.0")
    return {k: list(v) for k, v in main._EVC_TALLY.items()}


_BEFORE_COMMIT = ("[EVIDENCE-CENSUS] flush failed before its commit: 2 increment(s) merged back "
                  "(0 beyond the cap, counted as dropped); 0 dropped by the cap: ")


def _failed_before_commit(lines, state):
    return (len(lines) == 1 and lines[0].startswith(_BEFORE_COMMIT)
            and lines[0].endswith(" " + state))


def test_p4_a_failure_before_the_commit_merges_back(live, monkeypatch):
    monkeypatch.setattr(main, "_EVC_FLUSH_SQL", main._EVC_FLUSH_SQL.replace(
        "INSERT INTO evidence_refusal_daily ", "INSERT INTO evidence_refusal_daily_absent "))
    with _janitor_on(live, monkeypatch):
        earlier = _two_notes()
        before = live.run(_census(live.sm))
        lines = live.run(_flush_lines())
        rows = _delta(before, live.run(_census(live.sm)))
    assert _failed_before_commit(lines, "42P01"), lines            # the planted failure: no table
    assert {k: list(v) for k, v in main._EVC_TALLY.items()} == earlier and rows == {}


def test_p4_control_without_the_merge_back_the_batch_is_lost(live, monkeypatch):
    monkeypatch.setattr(main, "_EVC_FLUSH_SQL", main._EVC_FLUSH_SQL.replace(
        "INSERT INTO evidence_refusal_daily ", "INSERT INTO evidence_refusal_daily_absent "))
    monkeypatch.setattr(main, "_evc_merge_back", lambda batch: 0)
    with _janitor_on(live, monkeypatch):
        _two_notes()
        lines = live.run(_flush_lines())
    assert _failed_before_commit(lines, "42P01"), lines
    assert main._EVC_TALLY == {}


_COMMIT_DDL = """
CREATE OR REPLACE FUNCTION evc_probe_commit() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
  RAISE EXCEPTION 'evc_probe_commit_fails';
END $f$;
DROP TRIGGER IF EXISTS evc_probe_commit ON evidence_refusal_daily;
CREATE CONSTRAINT TRIGGER evc_probe_commit AFTER INSERT OR UPDATE ON evidence_refusal_daily
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION evc_probe_commit();
"""
_COMMIT_UNDO = ("DROP TRIGGER IF EXISTS evc_probe_commit ON evidence_refusal_daily; "
                "DROP FUNCTION IF EXISTS evc_probe_commit();")


async def _commit_fails(live):
    """The flush's COMMIT runs a deferred trigger that raises (P0001): the
    commit call itself fails, so the batch's fate is treated as unknown."""
    await _exec(live, _COMMIT_DDL)
    try:
        _two_notes()
        before = await _census(live.sm)
        lines = await _flush_lines()
        rows = _delta(before, await _census(live.sm))
    finally:
        await _exec(live, _COMMIT_UNDO)
    return lines, rows


def test_p4_a_failure_of_the_commit_drops_the_batch_and_prints_its_size(live, monkeypatch):
    with _janitor_on(live, monkeypatch):
        lines, rows = live.run(_commit_fails(live))
    assert len(lines) == 1 and lines[0].startswith(
        "[EVIDENCE-CENSUS] flush commit failed: 2 increment(s) in 1 key(s) dropped, not merged "
        "back; 0 dropped by the cap: ") and lines[0].endswith(" P0001"), lines
    assert main._EVC_TALLY == {} and rows == {}


async def _with_the_table_gone(live, coro_fn):
    await _exec(live, "ALTER TABLE evidence_refusal_daily RENAME TO evidence_refusal_daily_away")
    try:
        return await coro_fn()
    finally:
        await _exec(live, "ALTER TABLE evidence_refusal_daily_away RENAME TO evidence_refusal_daily")


def test_p4_the_table_absent_the_step_skips_and_keeps_the_tally(live, monkeypatch):
    with _janitor_on(live, monkeypatch):
        earlier = _two_notes()
        lines = live.run(_with_the_table_gone(live, _flush_lines))
    assert lines == [], lines
    assert {k: list(v) for k, v in main._EVC_TALLY.items()} == earlier
    assert main._EVC_TABLE_FOUND is False


def test_p4_control_without_the_probe_the_absent_table_fails_before_the_commit(live, monkeypatch):
    async def _found(db):
        return "found"
    monkeypatch.setattr(main, "_evc_table", _found)
    with _janitor_on(live, monkeypatch):
        earlier = _two_notes()
        lines = live.run(_with_the_table_gone(live, _flush_lines))
    assert _failed_before_commit(lines, "42P01"), lines
    assert {k: list(v) for k, v in main._EVC_TALLY.items()} == earlier


def _plant_a_bad_cell():
    """A tally cell whose count is not a number: the step fails AFTER the
    take, while it builds the batch's arrays (TypeError), before any write."""
    key = (datetime.now(timezone.utc).date(), "seat", 403, "signature", "1.41.0")
    main._EVC_TALLY[key] = ["evc_probe_not_a_count", datetime.now(timezone.utc)]
    return key


def test_p4_a_failure_after_the_take_reaches_the_merge_back_arm(live, monkeypatch):
    with _janitor_on(live, monkeypatch):
        key = _plant_a_bad_cell()
        lines = live.run(_flush_lines())
    assert lines == ["[EVIDENCE-CENSUS] flush failed before its commit: -1 increment(s) merged back "
                     "(0 beyond the cap, counted as dropped); 0 dropped by the cap: TypeError"], lines
    assert main._EVC_TALLY[key][0] == "evc_probe_not_a_count"     # the planted cell, merged back


def test_p4_control_the_take_outside_the_try_loses_the_batch(live, monkeypatch):
    src = _sources("_evc_flush_janitor_step")["_evc_flush_janitor_step"]
    moved = src.replace(
        "batch, dropped, committing = {}, 0, False\n        try:\n            batch, dropped = _evc_take()\n"
        "            keys = list(batch)\n            increments = sum(batch[k][0] for k in keys)\n",
        "batch, dropped = _evc_take()\n        keys = list(batch)\n"
        "        increments = sum(batch[k][0] for k in keys)\n        committing = False\n        try:\n")
    assert moved != src
    ns = {}
    exec(compile(moved, "evc_probe_mutant", "exec"), main.__dict__, ns)
    monkeypatch.setattr(main, "_evc_flush_janitor_step", ns["_evc_flush_janitor_step"])
    with _janitor_on(live, monkeypatch):
        _plant_a_bad_cell()
        with pytest.raises(TypeError) as ei:
            live.run(_flush_lines())
    assert "unsupported operand" in str(ei.value) and "str" in str(ei.value), ei.value
    assert main._EVC_TALLY == {}                                   # taken, then lost


def test_p4_an_empty_tally_executes_nothing(live, monkeypatch):
    opened = []

    def _no_session(*_a, **_k):
        opened.append(1)
        raise AssertionError("evc_probe: a session was opened for an empty tally")
    monkeypatch.setattr(database, "async_session", _no_session)
    lines = live.run(_flush_lines())
    assert opened == [] and lines == []


_SETTINGS_PROBE_SQL = """
    INSERT INTO evidence_refusal_daily (day, kind, status, field, mod_version, n, last_at)
    SELECT u.day, u.kind, u.status, u.field, u.mod_version, u.n, u.last_at
      FROM unnest(CAST(:day AS date[]), CAST(:k AS text[]), CAST(:s AS smallint[]),
                  CAST(:f AS text[]), CAST(:v AS text[]), CAST(:d AS bigint[]),
                  CAST(:t AS timestamptz[]))
           AS u(day, kind, status, field, mod_version, n, last_at)
     WHERE 1 = 1 / (CASE WHEN current_setting('lock_timeout') = '2s'
                          AND current_setting('statement_timeout') = '10s'
                          AND current_setting('synchronous_commit') = 'local' THEN 1 ELSE 0 END)
    ON CONFLICT (day, kind, status, field, mod_version) DO UPDATE
       SET n = evidence_refusal_daily.n + EXCLUDED.n
"""


async def _settings_probe(live):
    await _exec(live, "DELETE FROM evidence_refusal_daily WHERE field = 'signature'")
    _two_notes()
    lines = await _flush_lines()
    return lines, await _row(live.sm)


def test_p4_the_flush_runs_with_its_three_settings(live, monkeypatch):
    monkeypatch.setattr(main, "_EVC_FLUSH_SQL", _SETTINGS_PROBE_SQL)
    with _janitor_on(live, monkeypatch):
        lines, row = live.run(_settings_probe(live))
    assert lines == ["[EVIDENCE-CENSUS] flushed 2 increment(s) in 1 key(s); 0 dropped by the cap"]
    assert row["n"] == 2, row


def test_p4_control_without_the_settings_the_probe_fails(live, monkeypatch):
    monkeypatch.setattr(main, "_EVC_FLUSH_SQL", _SETTINGS_PROBE_SQL)
    monkeypatch.setattr(main, "_EVC_SETTINGS_SQL", "SELECT 1")
    with _janitor_on(live, monkeypatch):
        lines, row = live.run(_settings_probe(live))
    assert _failed_before_commit(lines, "22012"), lines            # division_by_zero: not in effect
    assert row is None


# -- P5: the janitor -------------------------------------------------------------------

CENSUS_STATEMENTS = [
    ("_evc_table", "explain", "SELECT to_regclass('evidence_refusal_daily') IS NOT NULL AS present"),
    ("_evc_flush_janitor_step", "explain", "SELECT set_config('lock_timeout', '2s', true), "
                                           "set_config('statement_timeout', '10s', true), "
                                           "set_config('synchronous_commit', 'local', true)"),
    ("_evc_flush_janitor_step", "explain", "INSERT INTO evidence_refusal_daily (day, kind, status, "
                                           "field, mod_version, n, last_at)"),
]


def _census_rows(rows):
    return [(r["func"], r["class"]) for r in rows if r["func"] in ("_evc_table", "_evc_flush_janitor_step")]


def test_p5_the_live_inventory_holds_the_flush_by_name_and_no_dynamic_site():
    inv = main._janitor_sql_inventory()
    assert inv["dynamic"] == [], inv["dynamic"]
    mine = [s for s in inv["statements"] if s["func"] in ("_evc_table", "_evc_flush_janitor_step")]
    got = sorted((s["func"], s["class"], " ".join(s["sql"].split())) for s in mine)
    want = sorted(CENSUS_STATEMENTS)
    assert len(got) == len(want), got
    for (f, c, sql), (wf, wc, wsql) in zip(got, want):
        assert (f, c) == (wf, wc) and sql.startswith(wsql), (f, c, sql)
    assert all("queue_cleanup_loop" in s["roots"] for s in mine), mine
    # every bind of every census statement is typed: the probe and the
    # settings statement have none at all ...
    for s in mine:
        if not s["sql"].lstrip().startswith("INSERT"):
            assert re.findall(r"(?<![:\w]):(\w+)", s["sql"]) == [], s
    # ... and the flush is ONE statement whose every bind is a typed array: no
    # bare :name outside a CAST(... AS <type>[])
    (flush,) = [s["sql"] for s in mine if s["sql"].lstrip().startswith("INSERT")]
    binds = re.findall(r"(?<![:\w]):(\w+)", flush)
    assert sorted(binds) == ["d", "day", "f", "k", "s", "t", "v"], binds
    assert all(re.search(r"CAST\(:%s AS \w+\[\]\)" % b, flush) for b in binds), flush
    assert "unnest(" in flush and "VALUES" not in flush, flush


async def _selftest(live, monkeypatch):
    monkeypatch.setattr(database, "async_session", live.sm)
    monkeypatch.setattr(main, "_janitor_selftest_report", {"status": "pending"})
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await main._run_janitor_query_selftest()
    return main._janitor_selftest_report, main._janitor_selftest_marker()


CENSUS_FUNCS = ("_evc_table", "_evc_flush_janitor_step")
_MISSING_RELATION = re.compile(r'relation "(\w+)" does not exist')


async def _relations_present(live, names):
    conn = await sl.sp.harness.connect_bound(sl.sp.DSN, live.case.schema)
    try:
        return [await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", n) for n in names]
    finally:
        await conn.close()


def test_p5_the_boot_self_test_checks_each_flush_statement_ok(live, monkeypatch):
    """The real boot self-test, run against this case's schema WITH 414,
    checks each census statement BY NAME and gives each the data statement's
    ok verdict, explained. This case's schema is not the full one: main's
    other janitor statements that need objects the case lacks fail here
    (today the FFA readmission ones), so the overall status is judged by the
    rule below and not pinned to ok. No failure may be a census statement's,
    every failure must be a missing relation (42P01) or column (42703), and
    every relation a 42P01 names must be absent from the case. The overall
    ok and janitor_selftest 1 with these same statements in the inventory is
    test_janitor_selftest_classes.py's
    test_pg_the_full_self_test_is_green_with_the_trading_schema, whose schema
    replays every numbered migration, 414 included."""
    report, word = live.run(_selftest(live, monkeypatch))
    rows = [o for o in report["outcomes"] if o["func"] in CENSUS_FUNCS]
    assert sorted((o["func"], o["outcome"], o["sql80"]) for o in rows) == sorted(
        (w[0], "explained", w[2][:80]) for w in CENSUS_STATEMENTS), rows
    assert report["timed_out"] == [] and report["db_error"] is None, report
    fails = report["failures"]
    assert [f for f in fails if f["func"] in CENSUS_FUNCS] == [], fails
    assert all(re.search(r"\[(42P01|42703)\]", f["error"]) for f in fails), fails
    named = [_MISSING_RELATION.findall(f["error"]) for f in fails if "[42P01]" in f["error"]]
    assert all(len(n) == 1 for n in named), named
    missing = sorted({n[0] for n in named})
    assert live.run(_relations_present(live, missing)) == [False] * len(missing), missing
    assert (report["status"], word) == (("failed", 0) if fails else ("ok", 1)), report["status"]


async def _selftest_then_the_step(live, monkeypatch):
    report, word = await _selftest(live, monkeypatch)
    return report, word, await _flush_lines()


def test_p5_control_the_table_gone_the_insert_fails_42P01_and_the_word_is_0(live, monkeypatch):
    """The table gone: the boot self-test reports the flush's INSERT failed
    with 42P01 (janitor_selftest 0), and the flush step, run right after in
    the same state, skips by its probe and keeps the tally."""
    earlier = _two_notes()
    report, word, lines = live.run(_with_the_table_gone(
        live, lambda: _selftest_then_the_step(live, monkeypatch)))
    assert lines == [] and main._EVC_TABLE_FOUND is False, lines
    assert {k: list(v) for k, v in main._EVC_TALLY.items()} == earlier
    rows = [o for o in report["outcomes"] if o["func"] in CENSUS_FUNCS]
    assert sorted((o["func"], o["outcome"], o["sql80"]) for o in rows) == sorted(
        (w[0], "failed" if w[2].startswith("INSERT") else "explained", w[2][:80])
        for w in CENSUS_STATEMENTS), rows
    (fail,) = [f for f in report["failures"] if f["func"] == "_evc_flush_janitor_step"]
    assert "[42P01]" in fail["error"] and "evidence_refusal_daily" in fail["error"], fail
    assert report["status"] == "failed" and word == 0, report["status"]


# -- P6: end to end once ---------------------------------------------------------------

async def _end_to_end(live, monkeypatch):
    await _exec(live, "DELETE FROM evidence_refusal_daily WHERE field = 'signature'")
    out = await _through_app(live, monkeypatch)
    lines = await _flush_lines()
    return out, lines, await _row(live.sm)


def test_p6_a_refused_record_then_one_janitor_step_writes_the_row(live, monkeypatch):
    with _janitor_on(live, monkeypatch):
        out, lines, row = live.run(_end_to_end(live, monkeypatch))
    assert out["status"] == 403 and out["delta"] == {("seat", 403, "signature", "1.41.0"): 1}, out
    assert out["rows"] == {}, out                                   # nothing written on the request path
    assert lines == ["[EVIDENCE-CENSUS] flushed 1 increment(s) in 1 key(s); 0 dropped by the cap"]
    assert row["n"] == 1 and main._EVC_TALLY == {}, row


# -- controls of the request path: one mutant each, judged by its own outcome ------------

def test_control_without_the_leave_a_refusal_counts_under_the_gate_field(live, monkeypatch):
    monkeypatch.setattr(main, "_evc_leave", lambda request, answer=None, field=None: answer)
    out = live.run(_through_app(live, monkeypatch))
    assert out["status"] == 403, out
    _once(out, ("seat", 403, "gate_other", "1.41.0"))


def test_control_without_the_settle_nothing_is_counted(live, monkeypatch):
    monkeypatch.setattr(main, "_evc_settle", lambda request, kind, status: None)
    out = live.run(_through_app(live, monkeypatch, version="1.0.0"))
    assert out["status"] == 426 and out["delta"] == {}, out


def test_control_without_the_version_rule_a_made_up_header_is_kept(monkeypatch):
    monkeypatch.setattr(main, "_evc_version", lambda r: r.headers.get("X-Mod-Version") or "other")
    main._evc_settle(_req("9.9.9", "signature"), "card", 403)
    assert _tally() == {("card", 403, "signature", "9.9.9"): 1}


def test_control_without_the_vocabulary_a_client_key_is_kept(monkeypatch):
    monkeypatch.setattr(main, "_evc_field", lambda f: f)
    answer = main.JSONResponse(status_code=422, content={"detail": "zz_made_up_key_9"})
    r = _req("1.41.0")
    main._evc_leave(r, answer)
    main._evc_settle(r, "seat", 422)
    assert _tally() == {("seat", 422, "zz_made_up_key_9", "1.41.0"): 1}


def test_control_without_the_401_rule_a_401_makes_a_second_row(monkeypatch):
    monkeypatch.setattr(main, "_evc_key", lambda status, field, request: (
        main._evc_field(field), main._evc_version(request)))
    assert _two_401s() == {("seat", 401, "seat_session", "1.41.0"): 1,
                           ("seat", 401, "unlisted", "other"): 1}


def test_control_without_the_settle_guard_a_failing_note_loses_the_answer(live, monkeypatch):
    planted = []

    def _raising_note(*_a):
        planted.append("evc_probe_note_fails")
        raise RuntimeError("evc_probe_note_fails")

    def _unguarded(request, kind, status):
        left = getattr(request.state, "evc_field", None)
        field, version = main._evc_key(status, left, request)
        main._evc_note(kind, status, field, version)
    monkeypatch.setattr(main, "_evc_note", _raising_note)
    monkeypatch.setattr(main, "_evc_settle", _unguarded)
    out = live.run(_through_app(live, monkeypatch))
    assert planted == ["evc_probe_note_fails"], planted
    assert out["status"] == 500 and out["delta"] == {}, out          # the 403 is lost
