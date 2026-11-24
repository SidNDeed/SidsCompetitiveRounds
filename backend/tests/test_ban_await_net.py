"""BAN-FIRST-1, RULING R1 K2: every act the ban census counts by its call is awaited.

ban_sweep_census.py and the ban lane's tests find a lock, a locker, a gate or
a ban read as an ast.Call of a name from the census's own lists
(RAISING_CALLS, the soft session check, the admin roster's _is_admin,
BAN_READS, SWEEP_GATE_READS, LOCK_CALLERS, IDENTITY_LOCKERS,
EXCLUSIVE_TAKERS_BY_NAME, the functions of SINGLE_KEY_TAKERS, RETURN_GUARDED
and INSERT_CORES), test_mdpl_gate_bound_pg's HELPER, or a name a ban lane
test counts by its call and no list holds (LANE_COUNTED), and an advisory
lock as an execute whose statement text holds one. A call of a
coroutine function that is not awaited runs nothing of its body; a count of
bare calls counts it all the same. This net holds that premise for every
such count at once, over the source text (no database):

  - in backend/api/*.py, every call of such a name, or of a coroutine
    function whose own body executes an advisory lock, and every execute or
    exec_driver_sql whose statement text (as the census reads it,
    StatementTexts) holds pg_advisory_lock, pg_advisory_xact_lock or their
    try forms, anywhere in a module, is the direct value of an Await, unless
    NOT_AWAITED lists it by module, function and name with its reason;
  - every name of those lists is defined in backend/api, and as a coroutine
    function, unless PLAIN lists it with its reason;
  - both lists are exact: an entry that no longer matches is a failure.

The negative control plants each kind of failure the net names.
"""

from __future__ import annotations

import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import ban_sweep_census as B  # noqa: E402

ADVISORY = re.compile(r"pg_(try_)?advisory_(xact_)?lock", re.I)
EXECUTES = frozenset({"execute", "exec_driver_sql"})

# Names of the census's lists that are plain functions: nothing to await.
PLAIN = {
    "_require_internal_key": "a plain function: it compares the internal key and raises; it returns no awaitable",
}

# Names a ban lane test counts by a bare call that no list of the census holds.
LANE_COUNTED = {
    "_mail_lock_identities": ("the unban's lock as test_ban_answers_pg's test_every_writer counts it; it locks "
                              "through _identity_lock_many, so the takers rule below does not find it"),
    "_ban_set_length_core": ("the length change's writer of player_bans, which test_every_writer counts by its "
                             "call (its one caller, and the core's lock before that call)"),
}

# (module, enclosing function, name): a call that is not the direct value of an Await, and why.
NOT_AWAITED = {
    ("main", "_region_pings_store", "_region_pings_store_task"): (
        "handed to asyncio.create_task: the task runs on its own session and takes the key there; the "
        "caller takes no lock and reads no ban"),
    ("auto_logs", "upload_auto_log", "_lock_and_count"): (
        "the first argument of an awaited asyncio.wait_for (the span's budget): the lock and count run under that "
        "await, and a timeout ends the transaction before the refusal"),
    ("main", "_pc_snapshot_boot_retake", "_pc_snapshot_janitor_step"): (
        "the first argument of an awaited asyncio.wait_for (the boot retake's bound): the step runs under that "
        "await, and a timeout leaves the retake to the janitor's first pass"),
}


def _bound_helper_name() -> str:
    """test_mdpl_gate_bound_pg.HELPER, read from that file's text (importing it imports the app)."""
    with open(os.path.join(HERE, "test_mdpl_gate_bound_pg.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    (v,) = [st.value.value for st in tree.body if isinstance(st, ast.Assign) and len(st.targets) == 1
            and getattr(st.targets[0], "id", None) == "HELPER" and isinstance(st.value, ast.Constant)]
    return v


def act_names() -> set:
    """Every name the ban lane's counts take as a lock, a locker, a gate or a
    ban read: the census's lists, its return-guarded helpers and insert cores,
    the deletion key's bounded taker that test_mdpl_gate_bound_pg counts, and
    LANE_COUNTED."""
    return (set(B.RAISING_CALLS) | {B.SOFT_CALL, "_is_admin"} | set(B.BAN_READS) | set(B.SWEEP_GATE_READS)
            | set(B.LOCK_CALLERS) | set(B.IDENTITY_LOCKERS) | set(B.EXCLUSIVE_TAKERS_BY_NAME)
            | {n for _m, n in B.SINGLE_KEY_TAKERS} | set(B.RETURN_GUARDED) | set(B.INSERT_CORES)
            | {_bound_helper_name()} | set(LANE_COUNTED))


def api_sources() -> dict:
    out = {}
    for fname in sorted(os.listdir(B.API)):
        if fname.endswith(".py"):
            with open(os.path.join(B.API, fname), encoding="utf-8") as fh:
                out[fname[:-3]] = fh.read()
    return out


def _owner(parent, node):
    q = node
    while q in parent:
        q = parent[q]
        if isinstance(q, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return q.name
    return "<module>"


def await_failures(sources, names, plain=None, listed=None):
    """sources: {module: source text}. (failures, keys, counts): failures as
    text; keys, the set of (kind, module, function, name) behind them;
    counts, the calls of the names and the advisory executes the walk read."""
    plain = PLAIN if plain is None else plain
    listed = NOT_AWAITED if listed is None else listed
    trees = {m: ast.parse(s) for m, s in sources.items()}
    texts = B.StatementTexts(trees)
    # the takers rule: a coroutine function whose own body executes an advisory lock is a locker too, and its calls
    # are held like the lists' names. At this writing it adds 32 names beyond the lists, main._pc_lock_blob among
    # them. A function that locks only through another locker (_mail_lock_identities, through _identity_lock_many)
    # is not found by it; LANE_COUNTED holds the one a lane test counts.
    takers = {fn.name for m, t in trees.items() for fn in B._functions(t) if isinstance(fn, ast.AsyncFunctionDef)
              and any(isinstance(c, ast.Call) and B._name_of(c) in EXECUTES
                      and ADVISORY.search(texts.call_text(m, c)) for c in B._own_nodes(fn))}
    names = set(names) | takers
    kinds, every = {}, names | set(plain)
    for t in trees.values():
        for n in ast.walk(t):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in every:
                kinds.setdefault(n.name, set()).add("async" if isinstance(n, ast.AsyncFunctionDef) else "def")
    out, keys, counts, seen = [], set(), {"calls": 0, "advisory": 0}, {}
    for name in sorted(every):
        k = kinds.get(name, set())
        if not k:
            out.append(f"{name}: counted by the census and defined nowhere in backend/api")
            keys.add(("undefined", "", "", name))
        elif name in plain and k != {"def"}:
            out.append(f"{name}: listed as a plain function and defined as {sorted(k)}")
            keys.add(("plain", "", "", name))
        elif name not in plain and k != {"async"}:
            out.append(f"{name}: a plain function, not listed in PLAIN")
            keys.add(("not-a-coroutine", "", "", name))
    for mod, tree in sorted(trees.items()):
        parent = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
        for c in ast.walk(tree):
            if not isinstance(c, ast.Call):
                continue
            nm = B._name_of(c)
            if nm in plain:
                continue
            if nm in names:
                counts["calls"] += 1
            elif nm in EXECUTES and ADVISORY.search(texts.call_text(mod, c)):
                counts["advisory"] += 1
            else:
                continue
            p = parent.get(c)
            if isinstance(p, ast.Await) and p.value is c:
                continue
            key = (mod, _owner(parent, c), nm)
            seen[key] = seen.get(key, 0) + 1
            if key not in listed or seen[key] > 1:
                out.append(f"{mod}.{key[1]}:{c.lineno}: {nm} is not the direct value of an Await: "
                           f"{ast.unparse(c)[:120]}")
                keys.add(("not-awaited",) + key)
    for key in sorted(set(listed) - set(seen)):
        out.append(f"{key[0]}.{key[1]}: {key[2]} listed as not awaited and not found so")
        keys.add(("stale",) + key)
    return out, keys, counts


def test_every_act_the_census_counts_by_its_call_is_awaited():
    names = act_names()
    out, _keys, counts = await_failures(api_sources(), names)
    assert out == [], "\n".join(out)
    # the walk reads what it is about (act_names() numbers 47 at this writing, the takers rule 32 more)
    assert len(names) >= 30 and counts["calls"] >= 250 and counts["advisory"] >= 50, (len(names), counts)


PLANTED = '''
import asyncio


async def _ban_gate_or_raise(db, sid, request=None):
    return None


async def _apply_ban_core(db, sid):
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:sid))"), {"sid": sid})


def _require_internal_key(k):
    return None


def _is_admin(db, sid):
    return True


async def route_bare(db, sid):
    _ban_gate_or_raise(db, sid)


async def route_wrapped(db, sid):
    await asyncio.wait_for(_ban_gate_or_raise(db, sid), 1)


async def route_lock_bare(db, sid):
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:sid))"), {"sid": sid})


async def route_lambda(db, sid):
    f = lambda: _apply_ban_core(db, sid)
    return f


async def route_clean(db, sid):
    await _ban_gate_or_raise(db, sid)
    await _apply_ban_core(db, sid)
    _require_internal_key(sid)


async def route_listed(db, sid):
    asyncio.create_task(_apply_ban_core(db, sid))


_ban_gate_or_raise(None, 1)
'''


def test_negative_control_each_kind_of_failure_is_named():
    names = {"_ban_gate_or_raise", "_apply_ban_core", "_is_admin", "_is_banned"}
    listed = {("m", "route_gone", "_is_banned"): "planted"}
    plain = {"_require_internal_key": "planted", "_apply_ban_core": "planted: it is a coroutine"}
    _out, keys, counts = await_failures({"m": PLANTED}, names, plain=plain, listed=listed)
    assert keys == {
        ("undefined", "", "", "_is_banned"),
        ("plain", "", "", "_apply_ban_core"),
        ("not-a-coroutine", "", "", "_is_admin"),
        ("not-awaited", "m", "route_bare", "_ban_gate_or_raise"),
        ("not-awaited", "m", "route_wrapped", "_ban_gate_or_raise"),
        ("not-awaited", "m", "route_lock_bare", "execute"),
        ("not-awaited", "m", "<module>", "_ban_gate_or_raise"),
        ("stale", "m", "route_gone", "_is_banned"),
    }, sorted(keys)
    # _apply_ban_core is planted as PLAIN here, so its calls (the lambda's, the listed task's) are not read:
    # the same tree with the true list names the lambda's call and keeps the task's entry
    _out, keys2, _ = await_failures({"m": PLANTED}, names, plain={"_require_internal_key": "planted"},
                                    listed={("m", "route_listed", "_apply_ban_core"): "planted"})
    assert ("not-awaited", "m", "route_lambda", "_apply_ban_core") in keys2, sorted(keys2)
    assert not any(k[0] in ("stale",) or k[2] == "route_listed" for k in keys2), sorted(keys2)
    assert not any(k[2] == "route_clean" for k in keys | keys2), sorted(keys | keys2)
    assert counts["advisory"] == 2, counts
