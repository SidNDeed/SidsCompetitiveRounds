"""The evidence refusal census (migration 414, evidence_refusal_daily), against
a real PostgreSQL (lane server-fix-1114, part B, fix 1).

  B1  each of the four intake routes: a refused record of each status the
      route can answer raises exactly one counter by one, under the expected
      kind, status and field; a stored record and its identical repeat raise
      none. The route's answer is the one the census-less route gives.
  B2  seat, with real records: stored (none), the repeat (none), a different
      record on the same key (409 conflict), a record naming a key the client
      made up (422; counted under `unlisted`, the answer unchanged).
  B3  bounds: a made-up or out-of-range version header lands on `other`; a 401
      cannot make a second row by changing its body or its header.
  B4  the census write failing leaves the answer unchanged and prints one line.
  B5  the table's CHECKs refuse a value outside each column's bound; the
      vocabulary; the wiring.
  F1  nothing the census does delays a decided answer by more than its budget
      (EVC_BUDGET_MS), whatever it waits on: the pool exhausted, the counter
      row locked, the statement slow, the commit slow or failing, a census
      that never returns. Afterwards no census task is left and the pool is
      whole. At most EVC_MAX_CONCURRENT census tasks exist; a further count is
      shed. The database bounds a census transaction (lock_timeout,
      statement_timeout).
  F2  through the whole ASGI app: every answer of 400..599 to a POST on an
      evidence path is counted exactly once, wherever it was decided (each
      place the middleware stack and the exception handlers can decide one).

Every control below runs one mutant and asserts the mutant's OWN outcome
(its status, its counted rows, its printed lines, its elapsed time), never
"some AssertionError was raised" (lesson 1187).

Built on seat_evidence_pg's case (every numbered migration replayed, so 414 is
in it) and the seat-evidence live helpers.
"""
import asyncio
import contextlib
import io
import json
import time

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import main  # noqa: E402
import seat_evidence as se  # noqa: E402
import seat_evidence_fixtures as fx  # noqa: E402
import test_seat_evidence_live as sl  # noqa: E402
from test_seat_evidence_live import live, signing  # noqa: E402,F401  (fixtures)

CA, CB, CX = "1000000000000801", "1000000000000802", "1000000000000899"   # CX: never registered

# The delivery bound asserted here. The budget is 0.3 s; the seats run at a
# load of about 17 on 4 processors, so the gap is wide, and every blocker
# below holds for at least ten times this limit (HOLD_S).
LIMIT_S = 1.5
HOLD_S = 20
CAP_S = 15          # a mutant's call is abandoned after ten times LIMIT_S

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


def _census_lines(lines):
    return [ln for ln in lines if ln.startswith("[EVIDENCE-CENSUS]")]


async def _drain(limit_s=8.0):
    """Wait until every census task has ended (bounded); the count left."""
    t_end = time.monotonic() + limit_s
    while main._EVC_TASKS and time.monotonic() < t_end:
        await asyncio.sleep(0.05)
    return len(main._EVC_TASKS), main._EVC_BUSY[0]


def _pooled(live, size, timeout=HOLD_S):
    """An engine on the case schema with a real pool, as the service's is
    (the case's own engine has no pool, so every census would connect)."""
    return create_async_engine(
        sl.sp.harness.async_dsn(sl.sp.DSN), pool_size=size, max_overflow=0, pool_timeout=timeout,
        connect_args={"server_settings": {"search_path": sl.sp.harness.quoted(live.case.schema)}})


@pytest.fixture(scope="module")
def census_engine(live):
    eng = _pooled(live, 2)
    yield eng
    live.run(eng.dispose())


@pytest.fixture(autouse=True)
def _no_census_task_crosses_a_test(live, census_engine, monkeypatch):
    """Every test starts with no census task, and leaves none behind; the
    census writes on a pooled engine of the case (_EVC_BIND), as in service
    on the app's pooled engine."""
    monkeypatch.setattr(main, "_EVC_BIND", census_engine)
    assert live.run(_drain()) == (0, 0)
    yield
    assert live.run(_drain()) == (0, 0)


def _not_counted(line, state):
    return (line.startswith("[EVIDENCE-CENSUS] seat 403 signature not counted: ")
            and line.endswith(" " + state))


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


def _answer(r):
    if isinstance(r, BaseException):
        return ("raised", type(r).__name__)
    if isinstance(r, dict):
        return (200, r)
    return (r.status_code, json.loads(r.body))


async def _call(sm, kind, token, version="1.41.0", body=None, cap=None, capture=True):
    """One call of the route itself: (answer, printed lines, a usable session
    afterwards (1), seconds taken). With `cap`, a call still running after it
    is abandoned and answers ("overran",). Calls run side by side pass
    capture=False and capture once around all of them (stdout is global)."""
    route = getattr(main, ROUTES[kind][0])
    req = sl.Req(body if body is not None else {"seat_steam_id": CA}, token, version=version)
    buf = io.StringIO()
    async with sm() as db:
        with (contextlib.redirect_stdout(buf) if capture else contextlib.nullcontext()):
            t0 = time.monotonic()
            try:
                if cap is None:
                    r = await route(req, db)
                else:
                    r = await asyncio.wait_for(route(req, db), cap)
            except asyncio.TimeoutError:
                r = None
            except Exception as e:  # noqa: BLE001 -- the 500 case asserts on it
                r = e
            took = time.monotonic() - t0
        try:                                                     # the route's session still answers
            alive = (await db.execute(text("SELECT 1"))).scalar()
        except Exception:  # noqa: BLE001
            alive = 0
    answer = ("overran",) if r is None else _answer(r)
    return answer, buf.getvalue().splitlines(), alive, took


async def _scenario(live, monkeypatch, kind, name, version="1.41.0"):
    plan, want = SCENARIOS[name]
    sm = live.sm
    await sl._players(sm, CA, CB)
    token = None if name == "401" else await sl._session(sm, CA)
    _patch(monkeypatch, kind, plan)
    before = await _census(sm)
    answer, lines, alive, took = await _call(sm, kind, token, version)
    await _drain()
    after = await _census(sm)
    return {"answer": answer, "delta": _delta(before, after), "lines": _census_lines(lines),
            "alive": alive, "took": took, "want": want}


def _b1_expected(kind, name):
    _plan, want = SCENARIOS[name]
    if want is None:
        return None
    status, field = want
    if field == "<off>":
        field = ROUTES[kind][3]
    version = "other" if status == 401 else "1.41.0"
    return {(kind, status, field, version): 1}


@pytest.mark.parametrize("name", sorted(SCENARIOS))
@pytest.mark.parametrize("kind", sorted(ROUTES))
def test_b1_each_refusal_raises_one_counter_and_a_stored_record_none(live, monkeypatch, kind, name):
    out = live.run(_scenario(live, monkeypatch, kind, name))
    assert out["alive"] == 1, out
    want = _b1_expected(kind, name)
    if want is None:
        assert out["answer"][0] == 200 and out["delta"] == {}, (kind, name, out)
        return
    status = SCENARIOS[name][1][0]
    assert out["delta"] == want, (kind, name, out)
    if status == 500:
        assert out["answer"] == ("raised", "RuntimeError"), out        # the same 500
    else:
        assert out["answer"][0] == status, out
        if name == "422_unlisted":                                     # the answer still names it
            assert out["answer"][1] == {"detail": "zz_made_up_key_9"}, out
    assert out["lines"] == [], out
    assert out["took"] < LIMIT_S, out


def test_b2_seat_real_records_stored_repeat_conflict_and_a_made_up_key(live, signing):
    key = "ranked_sevcen_000001"

    async def go():
        sm = live.sm
        await sl._players(sm, CA, CB)
        tok = await sl._session(sm, CA)
        out = []
        first = sl._body(CA, CB, key)
        for body in (first, first, sl._body(CA, CB, key, t0=12345)):
            before = await _census(sm)
            got = await sl._post(sm, body, tok)
            await _drain()
            out.append((got, _delta(before, await _census(sm))))
        rec = dict(fx.base_record())
        rec["zz_extra_key"] = 1
        bad = fx.envelope(rec, seat=CA, other=CB, stable="ranked_sevcen_000002",
                          text=json.dumps(rec, separators=(",", ":")))
        before = await _census(sm)
        got = await sl._post(sm, bad, tok)
        await _drain()
        out.append((got, _delta(before, await _census(sm))))
        return out
    out = live.run(go())
    assert out[0] == ((200, {"status": "recorded"}), {}), out[0]
    assert out[1] == ((200, {"status": "already_recorded"}), {}), out[1]
    assert out[2] == ((409, {"status": "conflict"}), {("seat", 409, "conflict", "1.41.0"): 1}), out[2]
    assert out[3] == ((422, {"detail": "zz_extra_key"}), {("seat", 422, "unlisted", "1.41.0"): 1}), out[3]


VERSIONS = [("1.41.0", "1.41.0"), (main.MIN_MOD_VERSION_EFFECTIVE, main.MIN_MOD_VERSION_EFFECTIVE),
            ("9.9.9", "other"), ("1.41.1", "other"), ("01.41.0", "other"), ("1.41.0x", "other"),
            ("1.41", "other"), ("", "other"), ("1.0.0", "other")]


@pytest.mark.parametrize("sent,stored", VERSIONS)
def test_b3_the_version_header_is_kept_only_inside_the_release_range(live, monkeypatch, sent, stored):
    out = live.run(_scenario(live, monkeypatch, "card", "403", version=sent))
    assert out["delta"] == {("card", 403, "signature", stored): 1}, (sent, out)


async def _two_401s(live):
    sm = live.sm
    before = await _census(sm)
    for body, version in (({"seat_steam_id": CA}, "1.41.0"),
                          ({"seat_steam_id": "1000000000000877", "x": "y" * 50}, "7.7.7")):
        await _call(sm, "seat", None, version=version, body=body)
    await _drain()
    return _delta(before, await _census(sm))


def test_b3_a_401_cannot_make_a_second_row_by_what_it_sends(live):
    delta = live.run(_two_401s(live))
    assert delta == {("seat", 401, "seat_session", "other"): 2}, delta


async def _failing_census(live, monkeypatch):
    monkeypatch.setattr(main, "_EVC_SQL", main._EVC_SQL.replace(
        "INSERT INTO evidence_refusal_daily", "INSERT INTO evidence_refusal_daily_absent"))
    return await _scenario(live, monkeypatch, "combat", "403")


def test_b4_a_failing_census_write_leaves_the_answer_unchanged(live, monkeypatch):
    out = live.run(_failing_census(live, monkeypatch))
    assert out["answer"] == (403, {"detail": "signature"}), out
    assert out["delta"] == {} and out["alive"] == 1, out
    assert len(out["lines"]) == 1 and "not counted" in out["lines"][0], out
    assert out["took"] < LIMIT_S, out


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


def test_b5_every_literal_refusal_field_of_the_four_modules_is_in_the_vocabulary(live):
    """The closed vocabulary covers every field the server authors as a
    literal (so `unlisted` is only ever a client-sent name or a composite this
    list misses, never a plain literal), the composed names, and the gate_*
    set of the outer layer."""
    import ast
    seen = set()
    for mod in {id(m): m for m, _p in main._EVC_KINDS.values()}.values():
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


def test_b5_the_four_routes_write_only_through_their_store_and_the_census(live):
    import inspect
    for kind, (route, attr, _n, _o) in ROUTES.items():
        src = inspect.getsource(getattr(main, route))
        assert "INSERT" not in src and "UPDATE" not in src and "db.add" not in src, route
        assert src.count('_evidence_refused(db, "%s", request,' % kind) == 5, route
        assert src.count('_evidence_census(db, "%s", request, 500, "internal")' % kind) == 1, route
        assert src.count("except HTTPException:") == 1, route
    assert "evidence_refusal_daily" in main._EVC_SQL and main._EVC_SQL.count("INSERT") == 1


def test_b5_each_kind_names_its_route_by_path(live):
    """_EVC_KINDS is the one line per kind: its module and the POST path of
    its route, which the outer layer reads."""
    for kind, (route, attr, _n, _o) in ROUTES.items():
        mod, path = main._EVC_KINDS[kind]
        assert mod is getattr(main, attr), kind
        hits = [r for r in main.app.routes if getattr(r, "path", None) == path
                and "POST" in getattr(r, "methods", ())]
        assert len(hits) == 1 and hits[0].endpoint is getattr(main, route), (kind, path)
    assert sorted(main._EVC_PATH_KINDS.values()) == sorted(ROUTES)


def test_b5_the_census_engine_in_service(live, monkeypatch):
    """With no test engine set: the route's census writes on the engine of the
    route's session (in its own session), the outer layer on the app's."""
    import database
    monkeypatch.setattr(main, "_EVC_BIND", None)
    db = live.sm()
    assert main._evc_engine(db) is db.bind is live.sm.kw["bind"]
    assert main._evc_engine(None) is database.engine


# -- F1: the census never delays a decided answer by more than its budget ------

def _seat_refusal(monkeypatch):
    _patch(monkeypatch, "seat", {"sig": False})                 # a 403 signature


async def _token(live):
    await sl._players(live.sm, CA, CB)
    return await sl._session(live.sm, CA)


async def _later_refusal_counts(live, monkeypatch):
    """A refusal after the blocker is gone is counted normally: the census
    and the pool are whole."""
    _seat_refusal(monkeypatch)
    tok = await _token(live)
    before = await _census(live.sm)
    answer, lines, _alive, took = await _call(live.sm, "seat", tok)
    await _drain()
    return answer, _delta(before, await _census(live.sm)), _census_lines(lines), took


LATER_OK = ((403, {"detail": "signature"}), {("seat", 403, "signature", "1.41.0"): 1}, [])


async def _pool_exhausted(live, monkeypatch, cap=None):
    """The census's pool has one connection and the route's own session holds
    it: the census waits for a checkout that would come after HOLD_S."""
    _seat_refusal(monkeypatch)
    tok = await _token(live)
    eng = _pooled(live, 1)
    saved = main._EVC_BIND
    monkeypatch.setattr(main, "_EVC_BIND", eng)       # the census on the route's one-connection pool
    sm1 = async_sessionmaker(eng, expire_on_commit=False)
    buf = io.StringIO()
    try:
        async with sm1() as db:
            req = sl.Req({"seat_steam_id": CA}, tok)
            with contextlib.redirect_stdout(buf):
                t0 = time.monotonic()
                try:
                    coro = main.submit_seat_evidence(req, db)
                    r = await (coro if cap is None else asyncio.wait_for(coro, cap))
                    answer = _answer(r)
                except asyncio.TimeoutError:
                    answer = ("overran",)
                took = time.monotonic() - t0
                await asyncio.sleep(1.0)                        # the cancel has had time to act
                leftover = len(main._EVC_TASKS)
        drained = await _drain()                                 # the blocker is released here
    finally:
        monkeypatch.setattr(main, "_EVC_BIND", saved)
        await eng.dispose()
    later = await _later_refusal_counts(live, monkeypatch)
    return {"answer": answer, "took": took, "lines": _census_lines(buf.getvalue().splitlines()),
            "leftover": leftover, "drained": drained, "later": later[:3]}


def test_f1_the_pool_exhausted_delays_the_answer_by_the_budget_only(live, monkeypatch):
    out = live.run(_pool_exhausted(live, monkeypatch))
    assert out["answer"] == (403, {"detail": "signature"}), out
    assert out["took"] < LIMIT_S, out
    assert out["lines"] == ["[EVIDENCE-CENSUS] budget seat 403 signature"], out
    assert out["leftover"] == 0 and out["drained"] == (0, 0), out
    assert out["later"] == LATER_OK, out


async def _row_locked(live, monkeypatch, budget_ms=None):
    """Another transaction holds the counter row this refusal raises."""
    _seat_refusal(monkeypatch)
    tok = await _token(live)
    await _call(live.sm, "seat", tok)                            # the row exists now
    await _drain()
    if budget_ms is not None:
        monkeypatch.setattr(main, "EVC_BUDGET_MS", budget_ms)
    conn = await sl.sp.harness.connect_bound(sl.sp.DSN, live.case.schema)
    try:
        tr = conn.transaction()
        await tr.start()
        await conn.execute("SELECT 1 FROM evidence_refusal_daily WHERE kind = 'seat' "
                           "AND status = 403 AND field = 'signature' FOR UPDATE")
        answer, lines, alive, took = await _call(live.sm, "seat", tok)
        await tr.rollback()
    finally:
        await conn.close()
    drained = await _drain()
    monkeypatch.setattr(main, "EVC_BUDGET_MS", 300)
    later = await _later_refusal_counts(live, monkeypatch)
    return {"answer": answer, "took": took, "lines": _census_lines(lines), "alive": alive,
            "drained": drained, "later": later[:3]}


def test_f1_a_locked_counter_row_delays_the_answer_by_the_budget_only(live, monkeypatch):
    out = live.run(_row_locked(live, monkeypatch))
    assert out["answer"] == (403, {"detail": "signature"}) and out["alive"] == 1, out
    assert out["took"] < LIMIT_S, out
    assert len(out["lines"]) == 1 and (
        out["lines"][0] == "[EVIDENCE-CENSUS] budget seat 403 signature"
        or _not_counted(out["lines"][0], "55P03")), out
    assert out["drained"] == (0, 0) and out["later"] == LATER_OK, out


SLOW_SQL = ("SELECT pg_sleep(%d), CAST(:k AS text), CAST(:s AS int), CAST(:f AS text), "
            "CAST(:v AS text)" % HOLD_S)


async def _slow_statement(live, monkeypatch, budget_ms=None):
    _seat_refusal(monkeypatch)
    tok = await _token(live)
    real = main._EVC_SQL
    monkeypatch.setattr(main, "_EVC_SQL", SLOW_SQL)
    if budget_ms is not None:
        monkeypatch.setattr(main, "EVC_BUDGET_MS", budget_ms)
    answer, lines, alive, took = await _call(live.sm, "seat", tok)
    drained = await _drain()
    monkeypatch.setattr(main, "_EVC_SQL", real)
    monkeypatch.setattr(main, "EVC_BUDGET_MS", 300)
    later = await _later_refusal_counts(live, monkeypatch)
    return {"answer": answer, "took": took, "lines": _census_lines(lines), "alive": alive,
            "drained": drained, "later": later[:3]}


def test_f1_a_slow_census_statement_delays_the_answer_by_the_budget_only(live, monkeypatch):
    out = live.run(_slow_statement(live, monkeypatch))
    assert out["answer"] == (403, {"detail": "signature"}) and out["alive"] == 1, out
    assert out["took"] < LIMIT_S, out
    assert out["lines"] == ["[EVIDENCE-CENSUS] budget seat 403 signature"], out
    assert out["drained"] == (0, 0) and out["later"] == LATER_OK, out


_COMMIT_DDL = """
CREATE OR REPLACE FUNCTION evc_probe_commit() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
  IF %s THEN PERFORM pg_sleep(%d); ELSE RAISE EXCEPTION 'evc_probe_commit_fails'; END IF;
  RETURN NULL;
END $f$;
DROP TRIGGER IF EXISTS evc_probe_commit ON evidence_refusal_daily;
CREATE CONSTRAINT TRIGGER evc_probe_commit AFTER INSERT OR UPDATE ON evidence_refusal_daily
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION evc_probe_commit();
"""
_COMMIT_UNDO = ("DROP TRIGGER IF EXISTS evc_probe_commit ON evidence_refusal_daily; "
                "DROP FUNCTION IF EXISTS evc_probe_commit();")


async def _at_commit(live, monkeypatch, slow):
    """The census's COMMIT runs a deferred trigger that sleeps HOLD_S (slow)
    or raises (failing)."""
    _seat_refusal(monkeypatch)
    tok = await _token(live)
    conn = await sl.sp.harness.connect_bound(sl.sp.DSN, live.case.schema)
    try:
        await conn.execute(_COMMIT_DDL % ("true" if slow else "false", HOLD_S))
        before = await _census(live.sm)
        answer, lines, alive, took = await _call(live.sm, "seat", tok)
        drained = await _drain()
        delta = _delta(before, await _census(live.sm))
    finally:
        await conn.execute(_COMMIT_UNDO)
        await conn.close()
    later = await _later_refusal_counts(live, monkeypatch)
    return {"answer": answer, "took": took, "lines": _census_lines(lines), "alive": alive,
            "drained": drained, "delta": delta, "later": later[:3]}


def test_f1_a_slow_commit_delays_the_answer_by_the_budget_only(live, monkeypatch):
    out = live.run(_at_commit(live, monkeypatch, slow=True))
    assert out["answer"] == (403, {"detail": "signature"}) and out["alive"] == 1, out
    assert out["took"] < LIMIT_S, out
    assert out["lines"] == ["[EVIDENCE-CENSUS] budget seat 403 signature"], out
    assert out["delta"] == {} and out["drained"] == (0, 0) and out["later"] == LATER_OK, out


def test_f1_a_failing_commit_leaves_the_answer_unchanged(live, monkeypatch):
    out = live.run(_at_commit(live, monkeypatch, slow=False))
    assert out["answer"] == (403, {"detail": "signature"}) and out["alive"] == 1, out
    assert out["took"] < LIMIT_S, out
    assert len(out["lines"]) == 1 and out["lines"][0].startswith(
        "[EVIDENCE-CENSUS] seat 403 signature not counted:"), out
    assert out["delta"] == {} and out["drained"] == (0, 0) and out["later"] == LATER_OK, out


async def _never_returns(*_a, **_k):
    await asyncio.Event().wait()


async def _every_refusal_with_a_stuck_census(live, monkeypatch, kind, cap=None):
    """The class: the census write replaced by one that never returns; every
    refusal path of `kind` answers within the limit, unchanged."""
    monkeypatch.setattr(main, "_evc_write", _never_returns)
    out = {}
    for name in REFUSALS:
        plan, want = SCENARIOS[name]
        await sl._players(live.sm, CA, CB)
        token = None if name == "401" else await sl._session(live.sm, CA)
        _patch(monkeypatch, kind, plan)
        answer, lines, alive, took = await _call(live.sm, kind, token, cap=cap)
        out[name] = (answer, _census_lines(lines), alive, took)
        if answer == ("overran",):
            # the abandoned call never reached its cancel: end its task here
            for t in list(main._EVC_TASKS):
                t.cancel()
            break
    out["drained"] = await _drain()
    return out


@pytest.mark.parametrize("kind", sorted(ROUTES))
def test_f1_class_a_census_that_never_returns_delays_no_refusal(live, monkeypatch, kind):
    out = live.run(_every_refusal_with_a_stuck_census(live, monkeypatch, kind))
    assert out.pop("drained") == (0, 0), out
    assert sorted(out) == REFUSALS
    for name, (answer, lines, alive, took) in out.items():
        status, field = SCENARIOS[name][1]
        field = ROUTES[kind][3] if field == "<off>" else field
        if status == 500:
            assert answer == ("raised", "RuntimeError"), (name, answer)
        else:
            assert answer[0] == status, (name, answer)
        assert took < LIMIT_S, (name, took)
        assert lines == ["[EVIDENCE-CENSUS] budget %s %d %s" % (kind, status, field)], (name, lines)
        assert alive == 1, name


_PROBE = "SELECT 'evc_r4_probe'"


def _stuck_holding_a_transaction(release):
    """A census write that opens its transaction, then neither returns nor
    ends on a cancel until `release` is set (a cancel that cannot reach the
    server at once): its slot stays held past the budget."""
    async def stuck(engine, *_a, **_k):
        async with main.AsyncSession(bind=engine) as s:
            await s.execute(text(_PROBE))
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await release.wait()
                raise
    return stuck


async def _three_at_once(live, monkeypatch):
    _seat_refusal(monkeypatch)
    tok = await _token(live)
    release = asyncio.Event()
    monkeypatch.setattr(main, "_evc_write", _stuck_holding_a_transaction(release))
    # one connection per census transaction, as many as are asked for
    monkeypatch.setattr(main, "_EVC_BIND", live.sm.kw["bind"])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        results = await asyncio.gather(
            *[_call(live.sm, "seat", tok, capture=False) for _ in range(3)])
        await asyncio.sleep(0.5)
    busy = (len(main._EVC_TASKS), main._EVC_BUSY[0])
    open_tx = await sl._scalar(
        live.sm, "SELECT count(*) FROM pg_stat_activity WHERE query = :q "
                 "AND state LIKE 'idle in transaction%'", q=_PROBE)
    release.set()
    drained = await _drain()
    lines = sorted(_census_lines(buf.getvalue().splitlines()))
    return {"answers": [r[0] for r in results], "took": max(r[3] for r in results),
            "busy": busy, "open_tx": open_tx, "lines": lines, "drained": drained}


def test_f1_at_most_two_census_transactions_and_a_third_is_shed(live, monkeypatch):
    out = live.run(_three_at_once(live, monkeypatch))
    assert out["answers"] == [(403, {"detail": "signature"})] * 3, out
    assert out["took"] < LIMIT_S, out
    assert out["busy"] == (2, 2) and out["open_tx"] == 2, out
    assert out["lines"] == ["[EVIDENCE-CENSUS] budget seat 403 signature"] * 2 + [
        "[EVIDENCE-CENSUS] shed seat 403 signature"], out
    assert out["drained"] == (0, 0), out


def _db_bound_lane(out, code):
    assert out["answer"] == (403, {"detail": "signature"}), out
    assert out["took"] < 4.0, out
    assert len(out["lines"]) == 1 and _not_counted(out["lines"][0], code), out


def test_f1_the_database_bounds_a_census_statement(live, monkeypatch):
    """With the budget far away (12 s), the census transaction's own
    statement_timeout ends a slow statement (57014) well inside it."""
    out = live.run(_slow_statement(live, monkeypatch, budget_ms=12000))
    _db_bound_lane(out, "57014")


def test_f1_the_database_bounds_a_census_lock_wait(live, monkeypatch):
    """With the budget far away (12 s), lock_timeout ends the wait for a held
    counter row (55P03) well inside it."""
    out = live.run(_row_locked(live, monkeypatch, budget_ms=12000))
    _db_bound_lane(out, "55P03")


# -- F2: every refusal of an evidence path is counted once, through the app ----

@contextlib.asynccontextmanager
async def _app(live, monkeypatch, get_db=None):
    """The whole ASGI app (every middleware and exception handler), its
    database the case's, its census on the case's pooled engine."""
    async def _db():
        async with live.sm() as s:
            yield s
    monkeypatch.setitem(main.app.dependency_overrides, main.get_db, get_db or _db)
    monkeypatch.setattr(main, "_RL_BUCKETS", main._rl_defaultdict(main._rl_deque))
    transport = httpx.ASGITransport(app=main.app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://evc.test") as client:
        yield client


async def _through_app(live, monkeypatch, kind="seat", plan=None, version="1.41.0", method="POST",
                       path=None, setup=None, get_db=None):
    await sl._players(live.sm, CA, CB)
    tok = await sl._session(live.sm, CA)
    _patch(monkeypatch, kind, plan if plan is not None else {"sig": False})
    if setup is not None:
        setup()
    headers = {"X-Session-Token": tok}
    if version is not None:
        headers["X-Mod-Version"] = version
    path = path or main._EVC_KINDS[kind][1]
    before = await _census(live.sm)
    buf = io.StringIO()
    async with _app(live, monkeypatch, get_db) as client:
        with contextlib.redirect_stdout(buf):
            t0 = time.monotonic()
            r = await client.request(method, path, json={"seat_steam_id": CA}, headers=headers)
            took = time.monotonic() - t0
    await _drain()
    return {"status": r.status_code, "delta": _delta(before, await _census(live.sm)),
            "lines": _census_lines(buf.getvalue().splitlines()), "took": took}


# The places that can decide an answer to a POST on an evidence path, derived
# from the app (outermost first), each with what it can answer there and the
# test that drives it. A layer added or removed fails the derivation test.
MIDDLEWARE = [
    ("evidence_key_gate", "answers only under /api/v1/internal/evidence-report/: none here"),
    ("replica_write_gate", "503 read_replica, only on a read replica: not countable there"),
    ("evidence_census_gate", "the outer count itself"),
    ("version_gate", "426 outdated: test_f2_version_gate_426"),
    ("maintenance_gate", "503 maintenance: test_f2_maintenance_gate_503"),
    ("rate_limit_gate", "413 payload_too_large, 429 rate_limited: test_f2_rate_limit_gate_*"),
    ("read_gate_cache_control", "never answers (adds a header to GET reads)"),
    ("CORSMiddleware", "answers only an OPTIONS preflight: not a POST"),
]
EXCEPTION_HANDLERS = [
    ("FfaReportRefusal", "raised only by the FFA report route: none here"),
    ("HTTPException", "a raised HTTPException's own status: test_f2_a_raised_http_exception"),
    ("RequestValidationError", "the four routes take no validated parameter: none here"),
    ("WebSocketRequestValidationError", "websocket only: none here"),
]
# Outside every handler: Starlette's ServerErrorMiddleware turns an error no
# handler took into a 500 (test_f2_an_unhandled_error_*, test_f2_the_framework_*).


def _layer_name(m):
    dispatch = (m.kwargs or {}).get("dispatch")
    return dispatch.__name__ if dispatch is not None else m.cls.__name__


def test_f2_the_places_that_can_answer_an_evidence_post_are_the_ones_classified(live):
    assert [_layer_name(m) for m in main.app.user_middleware] == [n for n, _w in MIDDLEWARE]
    assert sorted(getattr(k, "__name__", str(k)) for k in main.app.exception_handlers) == sorted(
        n for n, _w in EXCEPTION_HANDLERS)
    for kind, (route, *_r) in ROUTES.items():          # no validated parameter on the routes
        hit = next(r for r in main.app.routes if getattr(r, "path", None) == main._EVC_KINDS[kind][1])
        params = hit.dependant.query_params + hit.dependant.header_params + hit.dependant.body_params
        assert params == [], (kind, params)


@pytest.mark.parametrize("kind", sorted(ROUTES))
def test_f2_version_gate_426(live, monkeypatch, kind):
    out = live.run(_through_app(live, monkeypatch, kind=kind, version="1.0.0"))
    assert out["status"] == 426 and out["delta"] == {(kind, 426, "gate_version", "other"): 1}, out
    assert out["lines"] == [] and out["took"] < LIMIT_S, out


def test_f2_version_gate_426_without_a_header(live, monkeypatch):
    out = live.run(_through_app(live, monkeypatch, version=None))
    assert out["status"] == 426 and out["delta"] == {("seat", 426, "gate_version", "other"): 1}, out


def test_f2_maintenance_gate_503(live, monkeypatch):
    out = live.run(_through_app(live, monkeypatch,
                                setup=lambda: monkeypatch.setattr(main, "_in_maintenance", True)))
    assert out["status"] == 503 and out["delta"] == {("seat", 503, "gate_other", "1.41.0"): 1}, out


def test_f2_rate_limit_gate_413(live, monkeypatch):
    out = live.run(_through_app(live, monkeypatch,
                                setup=lambda: monkeypatch.setattr(main, "_RL_MAX_BODY", 8)))
    assert out["status"] == 413 and out["delta"] == {("seat", 413, "gate_size", "1.41.0"): 1}, out


def test_f2_rate_limit_gate_429(live, monkeypatch):
    def setup():
        monkeypatch.setattr(main, "_RL_GLOBAL", (0, 10.0))
        monkeypatch.setattr(main, "_RL_SENSITIVE", (0, 10.0))
    out = live.run(_through_app(live, monkeypatch, setup=setup))
    assert out["status"] == 429 and out["delta"] == {("seat", 429, "gate_rate", "1.41.0"): 1}, out


def test_f2_a_raised_http_exception(live, monkeypatch):
    out = live.run(_through_app(live, monkeypatch,
                                plan={"setting": HTTPException(status_code=409, detail="probe")}))
    assert out["status"] == 409 and out["delta"] == {("seat", 409, "gate_other", "1.41.0"): 1}, out


def test_f2_an_unhandled_error_before_the_routes_own_count(live, monkeypatch):
    async def boom(_request):
        raise RuntimeError("probe: before the route's try")
    out = live.run(_through_app(live, monkeypatch,
                                setup=lambda: monkeypatch.setattr(main, "_sev_claimed_seat", boom)))
    assert out["status"] == 500 and out["delta"] == {("seat", 500, "gate_other", "1.41.0"): 1}, out


def test_f2_the_framework_failing_a_dependency(live, monkeypatch):
    async def no_db():
        raise RuntimeError("probe: no database session")
        yield  # noqa: unreachable -- a generator dependency
    out = live.run(_through_app(live, monkeypatch, get_db=no_db))
    assert out["status"] == 500 and out["delta"] == {("seat", 500, "gate_other", "1.41.0"): 1}, out


def test_f2_a_route_counted_refusal_is_counted_once_through_the_stack(live, monkeypatch):
    out = live.run(_through_app(live, monkeypatch))
    assert out["status"] == 403 and out["delta"] == {("seat", 403, "signature", "1.41.0"): 1}, out


def test_f2_a_route_counted_500_is_counted_once_through_the_stack(live, monkeypatch):
    out = live.run(_through_app(live, monkeypatch, plan={"store": RuntimeError("probe")}))
    assert out["status"] == 500 and out["delta"] == {("seat", 500, "internal", "1.41.0"): 1}, out


def test_f2_control_an_accepted_record_counts_nothing_through_the_stack(live, monkeypatch):
    out = live.run(_through_app(live, monkeypatch, plan={}))
    assert out["status"] == 200 and out["delta"] == {}, out


def test_f2_a_wrong_method_and_an_unknown_path_are_not_evidence_refusals(live, monkeypatch):
    wrong = live.run(_through_app(live, monkeypatch, method="GET"))
    unknown = live.run(_through_app(live, monkeypatch, path="/api/v1/matches/seat-evidence-x"))
    assert (wrong["status"], wrong["delta"]) == (405, {}), wrong
    assert (unknown["status"], unknown["delta"]) == (404, {}), unknown


def test_f2_a_replica_refusal_is_not_counted(live, monkeypatch):
    """replica_write_gate is outside the census: on a read replica the
    database refuses every write, so no count can be made there."""
    out = live.run(_through_app(live, monkeypatch,
                                setup=lambda: monkeypatch.setattr(main, "IS_REPLICA", True)))
    assert out["status"] == 503 and out["delta"] == {}, out


# -- controls: one mutant each, judged by its own outcome ----------------------

def test_control_without_the_wiring_a_refusal_counts_nothing(live, monkeypatch):
    async def _plain(db, kind, request, answer):
        return answer
    monkeypatch.setattr(main, "_evidence_refused", _plain)
    out = live.run(_scenario(live, monkeypatch, "seat", "403"))
    assert out["answer"] == (403, {"detail": "signature"}) and out["delta"] == {}, out


def test_control_without_the_version_rule_a_made_up_header_is_kept(live, monkeypatch):
    monkeypatch.setattr(main, "_evc_version", lambda r: r.headers.get("X-Mod-Version") or "other")
    out = live.run(_scenario(live, monkeypatch, "card", "403", version="9.9.9"))
    assert out["delta"] == {("card", 403, "signature", "9.9.9"): 1}, out


def test_control_without_the_vocabulary_a_client_key_is_kept(live, monkeypatch):
    monkeypatch.setattr(main, "_evc_field", lambda f: f)
    out = live.run(_scenario(live, monkeypatch, "seat", "422_unlisted"))
    assert out["delta"] == {("seat", 422, "zz_made_up_key_9", "1.41.0"): 1}, out


def test_control_without_the_401_rule_a_401_makes_a_second_row(live, monkeypatch):
    monkeypatch.setattr(main, "_evc_key", lambda status, field, request: (
        main._evc_field(field), main._evc_version(request)))
    delta = live.run(_two_401s(live))
    assert delta == {("seat", 401, "seat_session", "1.41.0"): 1,
                     ("seat", 401, "seat_session", "other"): 1}, delta


def test_control_without_the_failure_isolation_the_answer_is_lost(live, monkeypatch):
    async def _bare(db, kind, request, status, field):
        f, v = main._evc_key(status, field, request)
        await db.execute(text(main._EVC_SQL), {"k": kind, "s": status, "f": f, "v": v})
    monkeypatch.setattr(main, "_evidence_census", _bare)
    out = live.run(_failing_census(live, monkeypatch))
    # the 403 is lost: the route raises the census's error instead
    assert out["answer"][0] == "raised" and out["delta"] == {}, out


def test_control_without_the_budget_the_answer_waits_on_the_census(live, monkeypatch):
    monkeypatch.setattr(main, "EVC_BUDGET_MS", 10 ** 8)
    out = live.run(_every_refusal_with_a_stuck_census(live, monkeypatch, "seat", cap=CAP_S))
    first = out[REFUSALS[0]]
    assert first[0] == ("overran",) and first[3] >= CAP_S, first      # abandoned after CAP_S


def test_control_without_the_cancel_the_census_task_is_left_behind(live, monkeypatch):
    monkeypatch.setattr(main, "_evc_cancel", lambda task: None)
    out = live.run(_pool_exhausted(live, monkeypatch))
    assert out["answer"] == (403, {"detail": "signature"}) and out["took"] < LIMIT_S, out
    assert out["leftover"] == 1, out                                  # still waiting for the pool


def test_control_without_the_concurrency_bound_nothing_is_shed(live, monkeypatch):
    monkeypatch.setattr(main, "EVC_MAX_CONCURRENT", 99)
    out = live.run(_three_at_once(live, monkeypatch))
    assert out["busy"] == (3, 3) and out["open_tx"] == 3, out
    assert out["lines"] == ["[EVIDENCE-CENSUS] budget seat 403 signature"] * 3, out


def test_control_without_the_statement_timeout_the_census_runs_to_the_budget(live, monkeypatch):
    monkeypatch.setattr(main, "_EVC_STATEMENT_TIMEOUT", "SELECT 1")
    out = live.run(_slow_statement(live, monkeypatch, budget_ms=12000))
    assert out["lines"] == ["[EVIDENCE-CENSUS] budget seat 403 signature"] and out["took"] >= 11.5, out


def test_control_without_the_lock_timeout_the_statement_timeout_ends_the_wait(live, monkeypatch):
    monkeypatch.setattr(main, "_EVC_LOCK_TIMEOUT", "SELECT 1")
    out = live.run(_row_locked(live, monkeypatch, budget_ms=12000))
    assert len(out["lines"]) == 1 and _not_counted(out["lines"][0], "57014"), out


def test_control_without_the_outer_count_a_gate_refusal_counts_nothing(live, monkeypatch):
    async def _none(request, kind, status):
        return None
    monkeypatch.setattr(main, "_evidence_census_outer", _none)
    out = live.run(_through_app(live, monkeypatch, version="1.0.0"))
    assert out["status"] == 426 and out["delta"] == {}, out


def test_control_without_the_flag_a_route_refusal_is_counted_twice(live, monkeypatch):
    real = main._evc_count

    async def _forgetful(engine, request, *a):
        request.state.evc_counted = False
        await real(engine, request, *a)
    monkeypatch.setattr(main, "_evc_count", _forgetful)
    out = live.run(_through_app(live, monkeypatch))
    assert out["status"] == 403, out
    assert out["delta"] == {("seat", 403, "signature", "1.41.0"): 1,
                            ("seat", 403, "gate_other", "1.41.0"): 1}, out
