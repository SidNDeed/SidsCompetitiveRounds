"""Rule T (rulings FOUR-R11-A3 (3), FOUR-R11-A4 (5), FOUR-R11-A5): the bound
behind the one rule T site of the walked code, main._group_region's
`at.timestamp()` (the "measured_at" value of members).

Rule T has two named pairs on the class datetime.datetime, taken by identity
with the method read from the class object: (datetime.datetime, timestamp)
gives float, (datetime.datetime, replace) gives datetime.datetime. The walk
(closed_walk.Bindings.rule_t) discharges a timestamp call whose result no
other rule proves only when it can show condition (i) of FOUR-R11-A5 (2):
the receiver is bound once by its root statement and otherwise only by the
pair statement `at = at.replace(...)` between the root and the site; it marks
the discharge in closed_walk.BOUND_MARKS. The receiver's ROOTS are taken as
given and observed here: (a) the driver's measured_at, read from PostgreSQL
by main's own query, and (b) the parameter current's value, built by main's
own writer. The replace result is DERIVED (by T1 and condition (i)) and needs
no observation of its own; the recorder stays armed at its statement and a
reach fails this test (condition (ii)).

A bound is an assertion that stays in the suite and held on the measured
flows, not a statement about every input.

What rule T claims, and what this test asserts, is the timestamp receiver
only: no walk refuses at rule T, and the walks' marks are the named table.
The a1 row's call of the group picker in _group_region still refuses after
rule T (ruling FOUR-R11-A14 (2), (3)): "a call of pick_region_for_group
whose members, a receiver of its deep methods, is members, which the walk
cannot prove builtin". That refusal is the first entry of a new kind in the
list of FOUR-R11-A10 (0): a parameter-derived value inside a container
(pmap from the parameters rows and current, home from rows, written into
the members dicts), handed to a receiver whose callee asks deep. It stays
open until that kind is ruled and built; this test neither asserts that the
row walks clean nor hides the refusal.

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
import types
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import closed_walk as _cw  # noqa: E402
import database  # noqa: E402
import identity_binder as _ib  # noqa: E402
import main  # noqa: E402
import test_a1_identity_formation as A1  # noqa: E402
import test_ffa_assembly_pg as A  # noqa: E402

# The sys.monitoring tool id of rule W/K's recorder
# (test_match_hold_admission_gate_pg._R11_TOOL), used here the same way and
# freed after each use; the test refuses when it is held.
_T_TOOL = 4
# The named table, frozen before the code (NOTES r11 t, premises): the one
# rule T site, (function, receiver, method), and the roots observed there.
_T_SITE = ("_group_region", "at", ".timestamp")
_T_ROOTS = ("a", "b")


class _TReq:
    """A verified request carrying a region-pings header (what
    main._region_pings_store reads: headers and state)."""

    def __init__(self, pings, gen):
        self.headers = {"X-Region-Pings": pings, "X-Region-Pings-Gen": gen}
        self.state = types.SimpleNamespace(scr_session_verified=True)


def _stmt_of(par, n):
    while n is not None and not isinstance(n, ast.stmt):
        n = par.get(id(n))
    return n


def _t_census():
    """Premise T2, read from main._group_region's own source at every run:
    the one timestamp call (the site, receiver `at`); `at` bound by exactly
    the root unpack and the pair statement; `stored` bound once to {} and
    stored into by exactly the driver row's statement and the overlay's
    statement, every other use the receiver of .get; `cat` bound once by the
    unpack of current; the driver row's `r` an element of res.mappings().
    Returns the file lines {site, root, pair, store_a, store_b}."""
    fn = main._group_region
    d = ast.parse(textwrap.dedent(inspect.getsource(fn.__code__))).body[0]
    off = fn.__code__.co_firstlineno - d.lineno
    par = {}
    for n in ast.walk(d):
        for c in ast.iter_child_nodes(n):
            par[id(c)] = n
    sites = [n for n in ast.walk(d) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "timestamp"]
    assert [ast.unparse(s) for s in sites] == ["at.timestamp()"], (
        "T2: the timestamp calls of _group_region", [ast.unparse(s) for s in sites])

    def binds(name):
        return [_stmt_of(par, n) for n in ast.walk(d) if isinstance(n, ast.Name)
                and n.id == name and not isinstance(n.ctx, ast.Load)]
    at = sorted(binds("at"), key=lambda s: s.lineno)
    assert [ast.unparse(s) for s in at] == [
        "pmap, at, _gen = stored.get(r['player_id'], (None, None, None))",
        "at = at.replace(tzinfo=timezone.utc)"], (
        "T2: the bindings of at", [ast.unparse(s) for s in at])
    cat = binds("cat")
    assert [ast.unparse(s) for s in cat] == ["cpid, cmap, cat, cgen = current"], (
        "T2: the bindings of cat", [ast.unparse(s) for s in cat])
    inits, stores, gets, other = [], [], [], []
    for n in ast.walk(d):
        if not (isinstance(n, ast.Name) and n.id == "stored"):
            continue
        p = par[id(n)]
        if isinstance(n.ctx, ast.Store):
            inits.append(p)
        elif (isinstance(p, ast.Subscript) and p.value is n
              and isinstance(p.ctx, ast.Store)):
            stores.append(par[id(p)])
        elif (isinstance(p, ast.Attribute) and p.attr == "get"
              and isinstance(par[id(p)], ast.Call) and par[id(p)].func is p):
            gets.append(par[id(p)])
        else:
            other.append((n.lineno + off, ast.unparse(p)))
    assert [ast.unparse(s) for s in inits] == ["stored = {}"], (
        "T2: the bindings of stored", [ast.unparse(s) for s in inits])
    stores = sorted(stores, key=lambda s: s.lineno)
    assert [ast.unparse(s) for s in stores] == [
        "stored[r['player_id']] = (r['pings'], r['measured_at'], gen)",
        "stored[cpid] = (cmap, cat, cgen)"], (
        "T2: the stores into stored", [ast.unparse(s) for s in stores])
    assert len(gets) == 2 and not other, ("T2: the other uses of stored",
                                          len(gets), other)
    loop = par.get(id(stores[0]))
    while loop is not None and not isinstance(loop, ast.For):
        loop = par.get(id(loop))
    assert loop is not None and ast.unparse(loop.target) == "r" and ast.unparse(
        loop.iter) == "res.mappings()", ("T2: the driver row's loop",
                                         loop and ast.unparse(loop.iter))
    return {"site": sites[0].lineno + off, "root": at[0].lineno + off,
            "pair": at[1].value.lineno + off, "store_a": stores[0].lineno + off,
            "store_b": stores[1].lineno + off}


def _t_marks():
    return sorted({m for m in _cw.BOUND_MARKS if m[0] == "T"}, key=repr)


def test_r11_t_bound_site_is_observed(monkeypatch):
    """Rule T's walk and its bound. (1) The interpreter has sys.monitoring.
    (2) T1 again under the suite, by identity. (4) W2: _group_region walked
    on its own under a recording grammar (the walker's own rules, the a1
    controls' structural route; the frozen grammar's order rule refuses any
    change to the function's statements before a walker rule speaks): no
    refusal of rule T. (3) T2, the census of the site's function, then
    W2's one rule T mark is the named one.
    (5) W1: the real a1 walks under the frozen grammar: the same mark, and
    no refusal of rule T (the row's members refusal is the A10 (0) list's
    entry, see the module docstring). (6) The flows of premise T4 run with
    a sys.monitoring CALL recorder on _group_region's code: at the site, the
    callable IS the class's timestamp, the receiver's type IS
    datetime.datetime, and each root is observed at least once; the pair
    statement is armed and a reach fails (condition (ii))."""
    assert hasattr(sys, "monitoring"), (
        "rule T's recorder needs sys.monitoring; this interpreter has none",
        sys.version)
    # (2) T1, by identity, under the suite
    cls = datetime.datetime
    assert type(cls) is type and cls.__flags__ & (1 << 8), "T1: the class"
    assert _ib.trusted(cls, "datetime", "datetime"), "T1: the class by name"
    assert main.datetime is cls and main.timezone is datetime.timezone, (
        "T1: main's names", main.datetime, main.timezone)
    for m in ("timestamp", "replace"):
        desc = vars(cls)[m]
        assert type(desc) is types.MethodDescriptorType, ("T1", m, type(desc))
        assert desc.__objclass__ is cls and _ib.trusted(
            desc, "datetime", "datetime." + m), ("T1", m)
        _cw.Bindings(main).t_pair(m, 0)
    # (4) W2: the structural route, before the census of (3), so that a
    # change to the site's function meets the walk's own rule first
    none = frozenset()
    rec = _cw.Grammar(none, none, none, A1._A1_CALLEES, record=True)
    monkeypatch.setattr(A1, "_A1_GRAMMAR", rec)
    monkeypatch.setattr(A1, "_POLICIES", {})
    _cw.reset_bound()
    try:
        A1._helper_effects(main._group_region)
        w2 = None
    except _cw.Unclassified as e:
        w2 = e.args[0]
    assert w2 is None or "rule T" not in str(w2), (
        "T W2: _group_region's own walk refuses at rule T's site", w2)
    w2_marks = _t_marks()
    # (3) T2
    c = _t_census()
    named = (main._group_region, c["site"], _T_SITE[2], _T_SITE[1],
             c["root"], (c["pair"],))

    def as_named(marks):
        return [(m[1], m[2], m[3], m[4], m[7], m[8]) for m in marks]
    assert as_named(w2_marks) == [named], ("T W2: rule T marks outside the "
                                           "named table", w2_marks, named)
    # (5) W1: the real a1 walks under the frozen grammar
    monkeypatch.setattr(A1, "_A1_GRAMMAR", A1._a1_grammar())
    monkeypatch.setattr(A1, "_POLICIES", {})
    _cw.reset_bound()
    walks = A1._a1_real_walks()
    hit = [(w, str(p)) for w, ps in walks for p in ps
           if "rule T" in str(p)]
    assert not hit, ("T W1: a real a1 walk refuses at rule T's site", hit)
    w1_marks = _t_marks()
    assert w1_marks == w2_marks, ("T W1: rule T marks", w1_marks, w2_marks)
    # (6) the bound, on the flows of T4
    mon = sys.monitoring
    assert mon.get_tool(_T_TOOL) is None, ("sys.monitoring tool id in use",
                                           mon.get_tool(_T_TOOL))
    gcode = main._group_region.__code__
    desc_ts = vars(cls)["timestamp"]
    armed = {c["site"]: "site", c["pair"]: "pair"}
    counts, bad, reached = collections.Counter(), [], []

    def line_of(off):
        for s, e, ln in gcode.co_lines():
            if s <= off and off < e:
                return ln
        return None

    def on_call(code, off, callee, arg0):
        # an exception raised here would surface inside _group_region,
        # whose own handler takes every Exception: it is recorded instead
        if code is not gcode:
            return None
        frame = sys._getframe(1)
        try:
            return observe(frame, code, off, callee, arg0)
        except Exception as exc:
            bad.append(("T: recorder error", repr(exc)))
            return None

    def observe(frame, code, off, callee, arg0):
        ln = line_of(off)
        kind = armed.get(ln)
        if kind is None:
            return None
        if frame.f_code is not code:
            bad.append(("T: not the monitored frame", ln))
            return None
        loc = frame.f_locals
        at = loc.get("at")
        if at is None or (arg0 is not at
                          and getattr(callee, "__self__", None) is not at):
            return None
        tn = type(at).__module__ + "." + type(at).__qualname__
        if type(at) is not cls:
            bad.append(("T: receiver type", ln, "at", tn))
        if kind == "pair":
            reached.append((ln, tn))
            return None
        if callee is not desc_ts:
            bad.append(("T: callee", ln, repr(callee)))
        cur, stored, r = loc.get("current"), loc.get("stored"), loc.get("r")
        ent = stored.get(r["player_id"]) if type(stored) is dict else None
        if cur is not None and at is cur[2]:
            root = "b"
        elif ent is not None and ent[1] is at:
            root = "a"
        else:
            root = None
            bad.append(("T: a value from no root", ln, tn))
        counts[(root, tn)] += 1
        return None

    async def body(env):
        lob = await env.lobby(4)
        monkeypatch.setattr(database, "async_session", env.sm)
        before = set(main._REGION_STORE_TASKS)
        got0 = await main._region_pings_store(
            _TReq("us=42,eu=31;age=12", "0a1b2c3d:1"), lob.sids[0], "r11t")
        new0 = set(main._REGION_STORE_TASKS) - before
        assert got0 is not None and len(new0) == 1, (
            "T4 flow: player 0's store", got0, len(new0))
        await asyncio.gather(*new0)
        before = set(main._REGION_STORE_TASKS)
        got1 = await main._region_pings_store(
            _TReq("us=55,eu=20;age=3", "4e5f6a7b:1"), lob.sids[1], "r11t")
        new1 = set(main._REGION_STORE_TASKS) - before
        assert got1 is not None and len(new1) == 1, (
            "T4 flow: player 1's store", got1, len(new1))
        for t in new1:
            t.cancel()
        await asyncio.gather(*new1, return_exceptions=True)
        n0, n1 = [await env.conn.fetchval(
            "SELECT count(*) FROM player_region_pings WHERE player_id = $1", p)
            for p in lob.pids[:2]]
        assert (n0, n1) == (1, 0), ("T4 flow: player 0's row landed and "
                                    "player 1's did not", n0, n1)
        rows = [{"player_id": p, "region": "eu"} for p in lob.pids[:2]]
        async with env.sm() as db:
            await main._group_region(db, rows[:1], "eu", "r11t")
        cur = main._region_current(lob.pids[1], got1)
        async with env.sm() as db:
            await main._group_region(db, rows, "eu", "r11t", current=cur)

    mon.use_tool_id(_T_TOOL, "r11 rule T bound")
    try:
        mon.register_callback(_T_TOOL, mon.events.CALL, on_call)
        mon.set_local_events(_T_TOOL, gcode, mon.events.CALL)
        A.run_env(monkeypatch, body, prefix="rt")
    finally:
        mon.set_local_events(_T_TOOL, gcode, 0)
        mon.register_callback(_T_TOOL, mon.events.CALL, None)
        mon.free_tool_id(_T_TOOL)
    # FOUR-R11-A9 (1)(e): the observations by class identity, per root
    # (shown in the warnings summary of every run)
    table = sorted(f"R11-T-COUNT T {c['site']} at root={root} {tn} {n}"
                   for (root, tn), n in counts.items())
    warnings.warn("; ".join(table) or "R11-T-COUNT none", UserWarning)
    # condition (ii) speaks first: a reach of the pair makes the site see the
    # replace result, which no root holds, so `bad` then carries that too;
    # both are shown
    assert not reached, (
        f"rule T: the branch at main:{c['pair']} (at.replace) is live: it was "
        "reached on a measured flow; the derived alternative is observed and "
        "must be listed as observed from now on", reached[:5], bad[:10])
    assert not bad, bad[:10]
    seen = {root for (root, _tn) in counts}
    missing = [x for x in _T_ROOTS if x not in seen]
    assert not missing, (f"rule T: the marked site main:{c['site']} has a root "
                         "no flow observed", missing, table)
