"""Rule N (rulings FOUR-R11-A10 (1), FOUR-R11-A14 (2)): the bound behind the
named members of the a1 gather rows.

The members, by name and nothing else (the a1 test's _N_TABLE):
  N1 volumes: the argument volumes at main._group_region's call of the group
     picker (region_pick.pick_region_for_group), row;
  N3 members: the argument members at the same call, deep;
  N4 detail: the receiver detail of the eleven `.get` calls of
     _group_region, the third element the picker returns, row; and N4 seats,
     its seat rows s at the four `s.get` calls of the generator over them;
  N5 current: the argument current of the call of _group_region in
     main.ovt_queue_poll and in main._ffa_queue_poll_inner, deep.
The walk (closed_walk._member_arg, _member_method, _n_discharge) takes from
source only a census, compared row by row with the frozen rows of the a1 test
(_N_CENSUS_ROWS), and assigns no provenance: each discharge is a mark
("N", F, site line, callee, name, group, label) in closed_walk.BOUND_MARKS.
This test walks the two gather rows (no refusal), checks the marks are the
named table, then runs the flows through main's own routes with rows read
from PostgreSQL under a sys.monitoring recorder that asserts, by identity, at
every marked site, the named classes of the value handed on (NOTES r11 n,
section 2, frozen before the code), attributes each observation to the
census's store or return it came from, and fails for a marked site no flow
reached and for a census row that must arrive and did not.

A bound is an assertion that stays in the suite and held on the measured
flows, not a statement about every input.

Stores and returns of the census that do not arrive on the measured flows
(NOTES r11 n, section 1; the recorder's assertion holds if one does): N1's
S1, the module literal (only when no query has succeeded in the process and
the query raises); N4's pick_region_for_group except return (only on an
exception inside the picker); _group_region's first binding of detail never
reaches a .get (the try rebinds it or its except does). _group_region's
except binding arrives on the error flow (_ovt_error_flow), the one flow that
reaches the .get at main:18767.

Member (2) of the brief, the result of match_hold._guard_identities, is not
built: its premise failed (NOTES r11 n, P-B4).

Runs under CF_TEST_PG_DSN as the other PostgreSQL suites. Needs
sys.monitoring (CPython 3.12+): without it the test fails, it never skips.
"""

import ast
import asyncio
import collections
import datetime
import inspect
import os
import sys
import textwrap
import warnings

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import closed_walk as _cw  # noqa: E402
import main  # noqa: E402
import test_a1_identity_formation as A1  # noqa: E402
import test_match_hold_admission_gate_pg as G  # noqa: E402
import test_match_hold_admission_routes_pg as R  # noqa: E402

# A free sys.monitoring tool id (rule T's and rule W/K's recorders use 4);
# the test refuses when it is held.
_N_TOOL = 3
_NONE = type(None)
# The named classes, frozen before the code (NOTES r11 n, section 2). "UUID"
# stands for the driver's class, taken from the loaded driver module and held
# by name and MRO as rule K's table holds it (G._r11_driver_uuid).
_N_NAMED = {
    "N1 volumes": ("row", (dict,)),
    "N3 members": ("deep", (list, dict, str, int, float, _NONE)),
    "N4 detail": ("row", (dict,)),
    "N4 seats": ("row", (dict,)),
    "N5 current ovt": ("deep", (tuple, _NONE, dict, str, int,
                                datetime.datetime, "UUID")),
    "N5 current ffa": ("deep", (tuple, _NONE, dict, str, int,
                                datetime.datetime, "UUID")),
}
# The census rows each observation is attributed to (the a1 test's
# _N_CENSUS_ROWS, by the line in its owner): every _N_MUST row is observed at
# least once; an _N_MAY row does not arrive on the measured flows (module
# docstring) and is admitted if it does.
_N_MUST = {
    "N1 volumes": ("store S2 _region_volumes:17", "return _region_volumes:12",
                   "return _region_volumes:20"),
    "N3 members": ("store _group_region:59",),
    "N4 detail": ("return _pick:48", "return _pick:92", "bind _group_region:71"),
    "N4 seats": ("return _pick:48", "return _pick:92"),
    "N5 current ovt": ("return _region_current:5", "return _region_current:6"),
    "N5 current ffa": ("return _region_current:5", "return _region_current:6"),
}
_N_MAY = {
    "N1 volumes": ("store S1 main:<module>",),
    "N4 detail": ("return pick_region_for_group:83",),
    "N4 seats": ("return pick_region_for_group:83", "bind _group_region:71"),
}
_PINGS = {"X-Region-Pings": "us=42,eu=31;age=12", "X-Region-Pings-Gen": "0a1b2c3d:1"}
# Captured at import, before any flow: the module literal's "volumes" entry
# (S1), when no query has filled the cache yet in this process.
_S1 = (main._REGION_VOLUMES_CACHE["volumes"]
       if main._REGION_VOLUMES_CACHE["at"] == 0.0 else None)


def _tree(fn):
    return ast.parse(textwrap.dedent(inspect.getsource(fn.__code__))).body[0]


def _calls(fn, pred):
    """File lines of the calls in fn's own source that `pred` takes."""
    d = _tree(fn)
    first = d.decorator_list[0].lineno if d.decorator_list else d.lineno
    off = fn.__code__.co_firstlineno - first
    return sorted(n.lineno + off for n in ast.walk(d)
                  if isinstance(n, ast.Call) and pred(n))


def _named_marks():
    """The marks the named table makes, derived from the source of each
    member's function: (label, function, line, callee, name, group)."""
    g = main._group_region
    pick = _calls(g, lambda n: isinstance(n.func, ast.Name)
                  and n.func.id == "_pick_region_for_group")
    assert len(pick) == 1, ("the picker calls of _group_region", pick)

    def gets(recv):
        return _calls(g, lambda n: isinstance(n.func, ast.Attribute)
                      and n.func.attr == "get"
                      and isinstance(n.func.value, ast.Name)
                      and n.func.value.id == recv)
    out = {("N1 volumes", g, pick[0], A1._N_PICK, "volumes", "row"),
           ("N3 members", g, pick[0], A1._N_PICK, "members", "deep")}
    out |= {("N4 detail", g, ln, ".get", "detail", "row") for ln in gets("detail")}
    out |= {("N4 seats", g, ln, ".get", "s", "row") for ln in gets("s")}
    for label, F in (("N5 current ovt", main.ovt_queue_poll),
                     ("N5 current ffa", main._ffa_queue_poll_inner)):
        site = _calls(F, lambda n: isinstance(n.func, ast.Name)
                      and n.func.id == "_group_region")
        assert len(site) == 1, (label, site)
        out.add((label, F, site[0], main._group_region, "current", "deep"))
    return out


def _n_walk(monkeypatch):
    """The two a1 gather rows walked from a fresh start under the frozen
    grammar: their problems, and the rule N marks as (label, function,
    line, callee, name, group)."""
    monkeypatch.setattr(A1, "_A1_GRAMMAR", A1._a1_grammar())
    problems, marks = [], set()
    for name in ("ovt_queue_poll", "_ffa_queue_poll_inner"):
        monkeypatch.setattr(A1, "_POLICIES", {})
        _cw.reset_bound()
        got = A1.formation_exit_violations(
            inspect.getsource(getattr(main, name)), "gather")
        problems += [(name, str(p)) for p in got]
        marks |= {(m[6], m[1], m[2], m[3], m[4], m[5])
                  for m in _cw.BOUND_MARKS if m[0] == "N"}
    return problems, marks


def _tname(t):
    return t.__module__ + "." + t.__qualname__


def _outside(v, named, path, out, counts, label):
    """Every object of v (deep: every element, key and value) whose class is
    not one of `named`, by path; counts each class seen."""
    t = type(v)
    counts[(label, path or "value", _tname(t))] += 1
    if not any(t is c for c in named):
        out.append((path or "value", _tname(t)))
        return
    if t is list or t is tuple:
        for x in v:
            _outside(x, named, path + "[]", out, counts, label)
    elif t is dict:
        for k, x in v.items():
            _outside(k, named, path + "{key}", out, counts, label)
            _outside(x, named, path + "{value}", out, counts, label)


async def _call(path, steam, extra):
    headers = {"X-Mod-Version": R.wiring.VERSION, "X-Session-Token": "tok:" + steam}
    headers.update(extra)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                 base_url="http://w", timeout=120) as cl:
        return await cl.request("GET", path, headers=headers)


async def _drain():
    await asyncio.gather(*list(main._REGION_STORE_TASKS), return_exceptions=True)


def _ovt_flow(header, mp):
    async def body(w, sm):
        ps = await R.hold_test.seed_players(w.conn, 3)
        for _, s in ps:
            await w.ok("POST", "/api/v1/ovt/queue/join", s, {"steam_id": s},
                       tag="ovt join")
        me = ps[0][1]   # the decider is the earliest joiner
        extra = _PINGS if header else {}
        if header:
            for _, s in ps[1:]:
                r = await _call("/api/v1/ovt/queue/poll/%s" % s, s, extra)
                assert r.status_code == 200, ("ovt poll", r.status_code, r.text[:300])
            await _drain()
        r = await _call("/api/v1/ovt/queue/poll/%s" % me, me, extra)
        assert r.status_code == 200, ("ovt decider", r.status_code, r.text[:300])
        await _drain()
    return body


def _ovt_error_flow(header, mp):
    """The decider's stored row (PostgreSQL) carries the header's nonce with
    no sequence, a row the table admits (307: both columns NULL-able, no
    check) and the store's upsert keeps (its WHERE is not true for a NULL
    sequence): _region_pings_newer then compares None with the header's
    sequence, the TypeError is caught by _group_region's except, and the
    pick line reads detail.get('error') (main:18767), the one .get site that
    only that branch reaches."""
    async def body(w, sm):
        ps = await R.hold_test.seed_players(w.conn, 3)
        for _, s in ps:
            await w.ok("POST", "/api/v1/ovt/queue/join", s, {"steam_id": s},
                       tag="ovt join")
        await w.conn.execute(
            "INSERT INTO player_region_pings (player_id, pings, measured_at,"
            " gen_nonce, gen_seq) VALUES ($1, '{\"eu\": 31}'::jsonb, now(),"
            " '0a1b2c3d', NULL)", ps[0][0])
        me = ps[0][1]
        r = await _call("/api/v1/ovt/queue/poll/%s" % me, me, _PINGS)
        assert r.status_code == 200, ("ovt decider", r.status_code, r.text[:300])
        await _drain()
    return body


def _ffa_flow(header, mp):
    async def body(w, sm):
        ps = await R.hold_test.seed_players(w.conn, 3)
        # the join stamps this module clock; registered so the test leaves
        # it as found (test_match_hold_admission_routes_pg._ffa_queue_poll)
        mp.setattr(main, "_ffa_gather_last_join_mono", main._ffa_gather_last_join_mono)
        for _, s in ps:
            await w.ok("POST", "/api/v1/ffa/queue/join", s, {"steam_id": s},
                       tag="ffa queue join")
        me = min((s for _, s in ps), key=main._ffa_sort_key)
        extra = _PINGS if header else {}
        if header:
            for _, s in ps:
                if s != me:
                    r = await _call("/api/v1/ffa/queue/poll/%s" % s, s, extra)
                    assert r.status_code == 200, ("ffa poll", r.status_code,
                                                  r.text[:300])
            await _drain()
        # the gather window: capped (waited past 120 s) and the pool seen now
        mp.setattr(main, "_ffa_gather_started_mono", main.time.monotonic() - 130)
        mp.setattr(main, "_ffa_gather_pool_seen_mono", main.time.monotonic())
        r = await _call("/api/v1/ffa/queue/poll/%s" % me, me, extra)
        assert r.status_code == 200, ("ffa leader", r.status_code, r.text[:300])
        await _drain()
    return body


# The measured flows (NOTES r11 n, P-A6): each through main.app's routes
# over ASGI with rows read from PostgreSQL, with and without the header.
_N_FLOWS = (("ovt header", _ovt_flow, True), ("ovt bare", _ovt_flow, False),
            ("ffa header", _ffa_flow, True), ("ffa bare", _ffa_flow, False),
            ("ovt error", _ovt_error_flow, True))


def test_r11_n_bound_sites_are_observed(monkeypatch):
    """Rule N's walk and its bound. (1) The interpreter has sys.monitoring.
    (2) The a1 gather rows walk with no problem, and their rule N marks are
    the named table. (3) The flows run with a recorder on the member sites'
    code: at each marked site the value handed on has the named classes
    (by identity, at every depth where the member is deep), each
    observation attributed to the census's store or return it came from; a
    marked site no flow reached fails, and so does a census row that must
    arrive and did not, or an observation from no census row."""
    assert hasattr(sys, "monitoring"), (
        "rule N's recorder needs sys.monitoring; this interpreter has none",
        sys.version)
    problems, marks = _n_walk(monkeypatch)
    assert not problems, ("rule N: the a1 gather rows refuse", problems[:5])
    named = _named_marks()
    assert marks == named, ("rule N: marks outside the named table",
                            sorted(map(repr, marks ^ named))[:10])
    mon = sys.monitoring
    assert mon.get_tool(_N_TOOL) is None, ("sys.monitoring tool id in use",
                                           mon.get_tool(_N_TOOL))
    gcode = main._group_region.__code__
    gx = [c for c in gcode.co_consts if isinstance(c, type(gcode))
          and c.co_name == "<genexpr>"]
    assert len(gx) == 1, ("the generator of _group_region", len(gx))
    gx = gx[0]
    rp = A1._n_rp
    rv, pk, pr, rc = (main._region_volumes.__code__, rp._pick.__code__,
                      rp.pick_region_for_group.__code__, main._region_current.__code__)
    gets = collections.defaultdict(list)
    pick_line = None
    for label, F, line, callee, name, _group in marks:
        if callee == ".get":
            gets[line].append((label, name))
        elif callee is A1._N_PICK:
            pick_line = line
    site_of = {main.ovt_queue_poll.__code__: "N5 current ovt",
               main._ffa_queue_poll_inner.__code__: "N5 current ffa"}
    seen, bad = collections.Counter(), []
    counts, origin = collections.Counter(), collections.Counter()
    tags, seat_src, last_rc = {}, {}, []

    def line_of(code, off):
        for s, e, ln in code.co_lines():
            if s <= off and off < e:
                return ln
        return None

    def named_ok(label, v):
        kind, classes = _N_NAMED[label]
        classes = tuple(G._r11_driver_uuid() if c == "UUID" else c
                        for c in classes)
        out = []
        if kind == "deep":
            _outside(v, classes, "", out, counts, label)
        else:
            counts[(label, "value", _tname(type(v)))] += 1
            if not any(type(v) is c for c in classes):
                out.append(("value", _tname(type(v))))
        if out:
            bad.append(("rule N: a class outside the named ones", label, out[:5]))

    def tagged(table, v):
        hit = table.get(id(v))
        return hit[1] if hit is not None and hit[0] is v else None

    def on_return(code, off, retval):
        try:
            ln = line_of(code, off) - code.co_firstlineno + 1
            if code is rv:
                loc = sys._getframe(1).f_locals
                cache = main._REGION_VOLUMES_CACHE
                if ("vols" in loc and cache["at"] == loc.get("now")
                        and cache["volumes"] is retval):
                    tags[id(retval)] = (retval, "store S2 _region_volumes:17")
                elif _S1 is not None and retval is _S1:
                    tags[id(retval)] = (retval, "store S1 main:<module>")
                tags[("ret", id(retval))] = (retval, f"return _region_volumes:{ln}")
            elif code is pk and type(retval) is tuple and len(retval) == 3:
                tags[id(retval[2])] = (retval[2], f"return _pick:{ln}")
            elif (code is pr and ln == 83 and type(retval) is tuple
                  and len(retval) == 3):
                tags[id(retval[2])] = (retval[2], f"return pick_region_for_group:{ln}")
            elif code is rc:
                last_rc.append((retval, f"return _region_current:{ln}"))
        except Exception as exc:
            bad.append(("rule N: recorder error (return)", repr(exc)))

    def on_start(code, off):
        try:
            if code is not gcode:
                return None
            frame = sys._getframe(1)
            caller = frame.f_back
            label = site_of.get(caller.f_code if caller is not None else None)
            if label is None:
                return None
            cur = frame.f_locals.get("current")
            src = next((t for v, t in reversed(last_rc) if v is cur), None)
            if src is None:
                bad.append(("rule N: current from no return of _region_current",
                            label))
            else:
                origin[(label, src)] += 1
            named_ok(label, cur)
            seen[(label, None)] += 1
        except Exception as exc:
            bad.append(("rule N: recorder error (start)", repr(exc)))
        return None

    def observe(label, ln, v, src):
        if src is None:
            bad.append(("rule N: a value from no census row", label, ln))
        else:
            origin[(label, src)] += 1
        named_ok(label, v)
        seen[(label, ln)] += 1

    def on_call(code, off, callee, arg0):
        try:
            if code is not gcode and code is not gx:
                return None
            frame = sys._getframe(1)
            if frame.f_code is not code:
                bad.append(("rule N: not the monitored frame", code.co_name))
                return None
            loc = frame.f_locals
            if code is gcode and callee is A1._N_PICK:
                if arg0 is not loc.get("members"):
                    bad.append(("rule N: the picker's members is not the frame's",))
                observe("N3 members", pick_line, arg0,
                        "store _group_region:59" if type(arg0) is list and arg0
                        else None)
                vol = loc.get("volumes")
                r = tags.get(("ret", id(vol)))
                if r is not None and r[0] is vol:
                    origin[("N1 volumes", r[1])] += 1
                observe("N1 volumes", pick_line, vol, tagged(tags, vol))
                return None
            if getattr(callee, "__name__", None) != "get":
                return None
            ln = line_of(code, off)
            for label, name in gets.get(ln, ()):
                v = loc.get(name, _cw._MISSING)
                if arg0 is not v and getattr(callee, "__self__", None) is not v:
                    continue
                if name == "detail":
                    src = tagged(tags, v) or (
                        "bind _group_region:71" if loc.get("why") == "error" else None)
                    for s in (v.get("seats") or []) if type(v) is dict else []:
                        seat_src[id(s)] = (s, src)
                else:
                    src = tagged(seat_src, v)
                observe(label, ln, v, src)
        except Exception as exc:
            bad.append(("rule N: recorder error (call)", repr(exc)))
        return None

    E = mon.events
    # main's own query fills the entry on the first flow (S2, return 20);
    # the stamp is set, never the value
    monkeypatch.setitem(main._REGION_VOLUMES_CACHE, "at", 0.0)
    mon.use_tool_id(_N_TOOL, "r11 rule N bound")
    try:
        mon.register_callback(_N_TOOL, E.CALL, on_call)
        mon.register_callback(_N_TOOL, E.PY_RETURN, on_return)
        mon.register_callback(_N_TOOL, E.PY_START, on_start)
        mon.set_local_events(_N_TOOL, gcode, E.CALL | E.PY_START)
        mon.set_local_events(_N_TOOL, gx, E.CALL)
        for code in (rv, pk, pr, rc):
            mon.set_local_events(_N_TOOL, code, E.PY_RETURN)
        for _name, make, header in _N_FLOWS:
            R._run(monkeypatch, make(header, monkeypatch))
    finally:
        for code in (gcode, gx, rv, pk, pr, rc):
            mon.set_local_events(_N_TOOL, code, 0)
        for ev in (E.CALL, E.PY_RETURN, E.PY_START):
            mon.register_callback(_N_TOOL, ev, None)
        mon.free_tool_id(_N_TOOL)
    # FOUR-R11-A9 (1)(e): the observations by class identity and by census
    # row, and each named class no observation had (the warnings summary)
    table = sorted(f"R11-N-COUNT {k[0]} {k[1]} {k[2]} {n}" for k, n in counts.items())
    table += sorted(f"R11-N-ORIGIN {k[0]} {k[1]} {n}" for k, n in origin.items())
    for label, (_kind, classes) in sorted(_N_NAMED.items()):
        names = {"asyncpg.pgproto.pgproto.UUID" if c == "UUID" else _tname(c)
                 for c in classes}
        got = {k[2] for k in counts if k[0] == label}
        table += [f"R11-N-NAMED-NOT-OBSERVED {label} {n}"
                  for n in sorted(names - got)]
    warnings.warn("; ".join(table) or "R11-N-COUNT none", UserWarning)
    assert not bad, bad[:10]
    unreached = sorted((m[0], m[1].__name__, m[2]) for m in marks
                       if not (seen[(m[0], m[2])] or seen[(m[0], None)]))
    assert not unreached, ("rule N: marked sites no flow observed", unreached)
    missing = sorted((label, row) for label, rows in _N_MUST.items()
                     for row in rows if not origin[(label, row)])
    assert not missing, ("rule N: census rows no flow observed", missing, table)
    stray = sorted(k for k in origin
                   if k[1] not in _N_MUST[k[0]] + _N_MAY.get(k[0], ()))
    assert not stray, ("rule N: observations from rows outside the census", stray)
