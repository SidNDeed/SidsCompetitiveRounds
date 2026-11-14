"""The evidence refusal census (migration 414, evidence_refusal_daily), against
a real PostgreSQL (lane server-fix-1114, part B).

  B1  each of the four intake routes: a refused record of each status the
      route can answer raises exactly one counter by one, under the expected
      kind, status and field; a stored record and its identical repeat raise
      none. The route's answer is the one the census-less route gives.
  B2  seat, with real records: stored (none), the repeat (none), a different
      record on the same key (409 conflict), a record naming a key the client
      made up (422; counted under `unlisted`, the answer unchanged).
  B3  bounds: a made-up or out-of-range version header lands on `other`; a 401
      cannot make a second row by changing its body or its header.
  B4  the census write failing leaves the answer unchanged, prints one line,
      and leaves the session usable; a counter row locked elsewhere delays a
      refusal by at most the lock timeout.
  B5  the table's CHECKs refuse a value outside each column's bound.

The controls at the bottom remove one rule each through main's module globals
and assert the rule's test then fails.

Built on seat_evidence_pg's case (every numbered migration replayed, so 414 is
in it) and the seat-evidence live helpers.
"""
import asyncio
import contextlib
import io
import json

import pytest
from sqlalchemy import text

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


async def _call(sm, kind, token, version="1.41.0", body=None):
    route = getattr(main, ROUTES[kind][0])
    req = sl.Req(body if body is not None else {"seat_steam_id": CA}, token, version=version)
    buf = io.StringIO()
    async with sm() as db:
        with contextlib.redirect_stdout(buf):
            try:
                r = await route(req, db)
            except Exception as e:  # noqa: BLE001 -- the 500 case asserts on it
                r = e
        try:                                                     # no failed transaction left
            alive = (await db.execute(text("SELECT 1"))).scalar()
        except Exception:  # noqa: BLE001 -- a control's mutant leaves one
            alive = 0
    lines = buf.getvalue().splitlines()
    if isinstance(r, BaseException):
        return ("raised", type(r).__name__), lines, alive
    if isinstance(r, dict):
        return (200, r), lines, alive
    return (r.status_code, json.loads(r.body)), lines, alive


async def _scenario(live, monkeypatch, kind, name, version="1.41.0"):
    plan, want = SCENARIOS[name]
    sm = live.sm
    await sl._players(sm, CA, CB)
    token = None if name == "401" else await sl._session(sm, CA)
    _patch(monkeypatch, kind, plan)
    before = await _census(sm)
    answer, lines, alive = await _call(sm, kind, token, version)
    after = await _census(sm)
    return answer, _delta(before, after), lines, alive, want


@pytest.mark.parametrize("name", sorted(SCENARIOS))
@pytest.mark.parametrize("kind", sorted(ROUTES))
def test_b1_each_refusal_raises_one_counter_and_a_stored_record_none(live, monkeypatch, kind, name):
    answer, delta, lines, alive, want = live.run(_scenario(live, monkeypatch, kind, name))
    assert alive == 1
    if want is None:
        assert answer[0] == 200 and delta == {}, (kind, name, answer, delta)
        return
    status, field = want
    if field == "<off>":
        field = ROUTES[kind][3]
    version = "other" if status == 401 else "1.41.0"
    assert delta == {(kind, status, field, version): 1}, (kind, name, answer, delta)
    if status == 500:
        assert answer == ("raised", "RuntimeError"), answer        # the same 500
    else:
        assert answer[0] == status, answer
        if name == "422_unlisted":                                   # the answer still names it
            assert answer[1] == {"detail": "zz_made_up_key_9"}, answer
    assert not [ln for ln in lines if ln.startswith("[EVIDENCE-CENSUS]")], lines


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
            out.append((await sl._post(sm, body, tok), _delta(before, await _census(sm))))
        rec = dict(fx.base_record())
        rec["zz_extra_key"] = 1
        bad = fx.envelope(rec, seat=CA, other=CB, stable="ranked_sevcen_000002",
                          text=json.dumps(rec, separators=(",", ":")))
        before = await _census(sm)
        out.append((await sl._post(sm, bad, tok), _delta(before, await _census(sm))))
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
    _answer, delta, _l, _a, _w = live.run(_scenario(live, monkeypatch, "card", "403", version=sent))
    assert delta == {("card", 403, "signature", stored): 1}, (sent, delta)


async def _two_401s(live):
    sm = live.sm
    before = await _census(sm)
    for body, version in (({"seat_steam_id": CA}, "1.41.0"),
                          ({"seat_steam_id": "1000000000000877", "x": "y" * 50}, "7.7.7")):
        await _call(sm, "seat", None, version=version, body=body)
    return _delta(before, await _census(sm))


def test_b3_a_401_cannot_make_a_second_row_by_what_it_sends(live):
    delta = live.run(_two_401s(live))
    assert delta == {("seat", 401, "seat_session", "other"): 2}, delta


async def _failing_census(live, monkeypatch):
    monkeypatch.setattr(main, "_EVC_SQL", main._EVC_SQL.replace(
        "INSERT INTO evidence_refusal_daily", "INSERT INTO evidence_refusal_daily_absent"))
    return await _scenario(live, monkeypatch, "combat", "403")


def test_b4_a_failing_census_write_leaves_the_answer_unchanged(live, monkeypatch):
    answer, delta, lines, alive, _w = live.run(_failing_census(live, monkeypatch))
    assert answer == (403, {"detail": "signature"}), answer
    assert delta == {} and alive == 1, (delta, alive)
    assert len([ln for ln in lines if ln.startswith("[EVIDENCE-CENSUS]")]) == 1, lines


async def _locked_row(live, monkeypatch):
    """Another transaction holds the counter row this refusal would raise."""
    sm = live.sm
    await _scenario(live, monkeypatch, "clock", "413")           # the row exists now
    conn = await sl.sp.harness.connect_bound(sl.sp.DSN, live.case.schema)
    try:
        tr = conn.transaction()
        await tr.start()
        await conn.execute("SELECT 1 FROM evidence_refusal_daily WHERE kind = 'clock' "
                           "AND status = 413 FOR UPDATE")
        token = await sl._session(sm, CA)
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        answer, lines, alive = await asyncio.wait_for(_call(sm, "clock", token), 5)
        took = loop.time() - t0
        await tr.rollback()
    finally:
        await conn.close()
    return answer, lines, alive, took


def test_b4_a_locked_counter_row_delays_a_refusal_by_at_most_the_lock_timeout(live, monkeypatch):
    answer, lines, alive, took = live.run(_locked_row(live, monkeypatch))
    assert answer == (413, {"detail": "record_bytes"}) and alive == 1, answer
    assert took < 2.0, took
    assert len([ln for ln in lines if ln.startswith("[EVIDENCE-CENSUS]")]) == 1, lines


@pytest.mark.parametrize("col,value", [("kind", "Seat"), ("status", 404), ("field", "A b"),
                                       ("field", "x" * 49), ("mod_version", "1.41.0.1"),
                                       ("mod_version", "100.0.0"), ("n", 0)])
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
        finally:
            await conn.close()
    live.run(go())


def test_b5_every_literal_refusal_field_of_the_four_modules_is_in_the_vocabulary(live):
    """The closed vocabulary covers every field the server authors as a
    literal (so `unlisted` is only ever a client-sent name or a composite this
    list misses, never a plain literal), and the composed names."""
    import ast
    seen = set()
    for mod in {id(m): m for m in main._EVC_KINDS.values()}.values():
        tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", ""))
                    in ("EvidenceRefused", "Refusal") and len(n.args) >= 2
                    and isinstance(n.args[1], ast.Constant)):
                seen.add(n.args[1].value)
    assert seen and seen <= main._EVC_FIELDS, sorted(seen - main._EVC_FIELDS)
    assert {"hit_sent.reset_keyed_since", "ldir.plugins", "seat_session"} <= main._EVC_FIELDS
    assert "zz_made_up_key_9" not in main._EVC_FIELDS


def test_b5_the_four_routes_write_only_through_their_store_and_the_census(live):
    import inspect
    for kind, (route, attr, _n, _o) in ROUTES.items():
        src = inspect.getsource(getattr(main, route))
        assert "INSERT" not in src and "UPDATE" not in src and "db.add" not in src, route
        assert src.count('_evidence_refused(db, "%s", request,' % kind) == 5, route
        assert src.count('_evidence_census(db, "%s", request, 500, "internal")' % kind) == 1, route
    assert "evidence_refusal_daily" in main._EVC_SQL and main._EVC_SQL.count("INSERT") == 1


# -- negative controls: remove one rule, its test fails ------------------------

def _fails(fn, *a):
    with pytest.raises(AssertionError):
        fn(*a)


def test_control_without_the_wiring_a_refusal_counts_nothing(live, monkeypatch):
    async def _plain(db, kind, request, answer):
        return answer
    monkeypatch.setattr(main, "_evidence_refused", _plain)
    _fails(test_b1_each_refusal_raises_one_counter_and_a_stored_record_none,
           live, monkeypatch, "seat", "403")


def test_control_without_the_version_rule_a_made_up_header_is_kept(live, monkeypatch):
    monkeypatch.setattr(main, "_evc_version", lambda r: r.headers.get("X-Mod-Version") or "other")
    _fails(test_b3_the_version_header_is_kept_only_inside_the_release_range,
           live, monkeypatch, "9.9.9", "other")


def test_control_without_the_vocabulary_a_client_key_is_kept(live, monkeypatch):
    monkeypatch.setattr(main, "_evc_field", lambda f: f)
    _fails(test_b1_each_refusal_raises_one_counter_and_a_stored_record_none,
           live, monkeypatch, "seat", "422_unlisted")


def test_control_without_the_401_rule_a_401_makes_a_second_row(live, monkeypatch):
    monkeypatch.setattr(main, "_evc_key", lambda status, field, request: (
        main._evc_field(field), main._evc_version(request)))
    _fails(test_b3_a_401_cannot_make_a_second_row_by_what_it_sends, live)


def test_control_without_the_failure_isolation_the_answer_is_lost(live, monkeypatch):
    async def _bare(db, kind, request, status, field):
        f, v = main._evc_key(status, field, request)
        await db.rollback()
        await db.execute(text(main._EVC_SQL), {"k": kind, "s": status, "f": f, "v": v})
        await db.commit()
    monkeypatch.setattr(main, "_evidence_census", _bare)
    _fails(test_b4_a_failing_census_write_leaves_the_answer_unchanged, live, monkeypatch)


def test_control_without_the_lock_timeout_a_refusal_waits_on_the_row(live, monkeypatch):
    monkeypatch.setattr(main, "_EVC_LOCK_TIMEOUT", "SELECT 1")
    with pytest.raises((AssertionError, asyncio.TimeoutError)):
        test_b4_a_locked_counter_row_delays_a_refusal_by_at_most_the_lock_timeout(live, monkeypatch)
