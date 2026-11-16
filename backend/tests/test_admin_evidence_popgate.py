"""AER-POPGATE-1: the evidence report's population cache has a fixed byte
allowance (POP_CACHE_MAX_MB) and reads nothing of the process; the display
population is built once after start through the report's own path; /health
carries the outcome of the most recent build attempt
(`admin_evidence_population`, a closed set of words) and the batch's build
marker (`aer_popgate_build`).

No database: the rebuild statement is replaced where a test needs a build,
and the recovery probe where a test needs a role. The route-level proof on a
live PostgreSQL (a fresh cache in a 475.8 MB process admits and serves) is
test_admin_evidence_routes_pg.py::test_popgate_a_fresh_cache_in_a_large_process_admits_the_display_population.
"""
import ast
import asyncio
import inspect
import logging
import os
import sys
from array import array

import pydantic
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import admin_evidence as ae  # noqa: E402

API = os.path.join(HERE, "..", "api", "admin_evidence.py")

# The worst case the allowance's derivation states beside POP_CACHE_MAX_MB.
WORST_CASE_BYTES = 15923456


def _worst_case_cache():
    """The cache at its worst case (design 2.6): 4 live and 4 leased-retired
    game sets, one replacement in progress, 8 live and 4 leased-retired window
    sources at one value per unit, the memo at WIN_DERIVED_BYTES_MAX."""
    P = ae.AER_CONTRACT_BOUNDS["POP_VALUES_MAX"]
    W = ae.AER_CONTRACT_BOUNDS["WIN_VALUES_MAX"]
    R = sum(1 for e in ae.REPORT_REGISTRY if not e.is_window and e.ranked)
    cache = ae.PopulationCache()

    def vals(n):
        return {k: array("d", bytes(8 * n)) for k in range(R)}

    def offs(n):
        return {k: array("i", bytes(4 * (n + 1))) for k in range(R)}

    for i in range(4):
        cache.lease(cache.publish(("g", i), vals(P), {}))
        cache.publish(("g", i), vals(P), {})
    replacement = vals(P)
    cache.in_progress = sum(len(a) * 8 for a in replacement.values())
    for i in range(8):
        if i < 4:
            cache.lease(cache.publish(("w", i), vals(W), {}, offsets=offs(W)))
        cache.publish(("w", i), vals(W), {}, offsets=offs(W))
    lease = cache.current(("w", 0))
    for j in range(32):
        cache.memo_put(("c", j), lease, {"d": array("d", bytes(65536))}, 65536)
    return cache


def test_the_worst_case_cache_fits_the_allowance():
    """Ruling 3(c): the worst-case cache, built as the derivation states it,
    fits the gate's allowance, which is POP_CACHE_MAX_MB MiB."""
    cache = _worst_case_cache()
    assert (len(cache.live), len(cache.retired)) == (12, 8)
    assert cache.budget == ae.AER_CONTRACT_BOUNDS["POP_CACHE_MAX_MB"] * 1024 * 1024
    assert cache.cache_bytes() == WORST_CASE_BYTES, (
        "the worst case moved from the derivation's figure: re-derive POP_CACHE_MAX_MB",
        cache.cache_bytes())
    assert cache.cache_bytes() <= cache.budget, (cache.cache_bytes(), cache.budget)
    print("GATE popgate worst case: %d counted bytes within the %d-byte allowance (%d MiB)"
          % (cache.cache_bytes(), cache.budget, ae.AER_CONTRACT_BOUNDS["POP_CACHE_MAX_MB"]))


def test_the_allowance_reads_nothing_of_the_process(monkeypatch):
    """Ruling 2: the cache takes no process figure, and a process figure
    patched in (475.8 MB, the live refusal's) does not move the allowance."""
    assert list(inspect.signature(ae.PopulationCache).parameters) == ["clock"]
    want = ae.AER_CONTRACT_BOUNDS["POP_CACHE_MAX_MB"] * 1024 * 1024
    monkeypatch.setattr(ae, "process_rss_mb", lambda peak=False: 475.8, raising=False)
    monkeypatch.setattr(ae, "_CACHE", [None])
    assert ae._aer_cache().budget == want
    with open(API, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    names |= {a.arg for n in ast.walk(tree) if isinstance(n, ast.arguments)
              for a in n.args + n.kwonlyargs}
    gone = {"process_rss_mb", "base_rss_mb", "budget_bytes", "SIZING_BASE_RSS_MB",
            "BASE_RSS_FLOOR_MB"}
    assert not names & gone, names & gone
    assert "POP_MEM_BUDGET_MB" not in ae.AER_CONTRACT_BOUNDS


def test_the_word_set_is_closed_and_each_refusal_has_its_word():
    """Ruling 5: the words /health can carry, the refusal classes of the
    code mapped onto them, and every PopulationUnavailable raised in the
    module carrying one of those classes."""
    assert ae.POPULATION_WORDS == ("pending", "ready", "unavailable:budget",
                                   "unavailable:duplicate", "unavailable:deadline",
                                   "unavailable:error")
    with open(API, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    reasons = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "PopulationUnavailable":
            assert len(n.args) == 2 and isinstance(n.args[1], ast.Constant), ast.unparse(n)
            reasons.append(n.args[1].value)
    assert sorted(reasons) == ["budget", "duplicate", "duplicate"], reasons
    out = ae._population_outcome
    assert out(ae.PopulationUnavailable("x", "budget")) == "unavailable:budget"
    assert out(ae.PopulationUnavailable("x", "duplicate")) == "unavailable:duplicate"
    assert out(asyncio.CancelledError()) == "unavailable:deadline"
    assert out(asyncio.TimeoutError()) == "unavailable:deadline"
    assert out(RuntimeError("x")) == "unavailable:error"
    assert out(ae.PopulationUnavailable("x", "other")) == "unavailable:error"


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


@pytest.fixture()
def fresh(monkeypatch):
    """A fresh cache, word and rebuild slot; a primary unless a test says;
    a report deadline of 0.2 s so a refusal at the deadline is quick."""
    monkeypatch.setattr(ae, "_CACHE", [None])
    monkeypatch.setattr(ae, "_POP_STATE", ["pending"])
    monkeypatch.setattr(ae, "_REBUILDING", [False])
    monkeypatch.setitem(ae.AER_CONTRACT_BOUNDS, "REPORT_DEADLINE_S", 1.2)
    monkeypatch.setitem(ae.AER_CONTRACT_BOUNDS, "AUDIT_RESERVE_S", 1)
    calls = []

    async def primary(db):
        return False

    monkeypatch.setattr(ae, "_in_recovery", primary)
    return calls


def _rebuild(monkeypatch, calls, result=None, exc=None, sleep=0.0):
    async def rebuild(conn, key, pop_days, lag_s, ranked_only=False, cap=None):
        calls.append(key)
        if sleep:
            await asyncio.sleep(sleep)
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr(ae, "rebuild_game_population", rebuild)


def _warm(caplog):
    with caplog.at_level(logging.INFO, logger="admin_evidence"):
        got = asyncio.run(ae.warm_display_population(session_factory=_Session, delay_s=0))
    lines = [r.getMessage() for r in caplog.records if "population warm-up" in r.getMessage()]
    return got, lines


def test_the_warm_up_builds_and_publishes_the_display_population(monkeypatch, fresh, caplog):
    _rebuild(monkeypatch, fresh, result=({0: array("d", [1.0, 2.0])}, {}))
    assert ae.population_health_word() == "pending"
    got, lines = _warm(caplog)
    cache = ae._CACHE[0]
    assert got == "ready" and ae.population_health_word() == "ready"
    assert fresh == [ae._display_key()] and list(cache.live) == [ae._display_key()]
    assert all(g.leases == 0 for g in cache.live.values()) and ae._REBUILDING == [False]
    assert len(lines) == 1 and lines[0].startswith(
        "admin_evidence population warm-up: ready gen=1 duration_ms="), lines


@pytest.mark.parametrize("label,kw,word", [
    ("duplicate", {"exc": ae.PopulationUnavailable("population x: 1 repeated", "duplicate")},
     "unavailable:duplicate"),
    ("error", {"exc": RuntimeError("the statement failed")}, "unavailable:error"),
    ("deadline", {"result": ({0: array("d", [1.0])}, {}), "sleep": 5.0},
     "unavailable:deadline"),
])
def test_each_failed_warm_up_names_its_class_and_never_raises(monkeypatch, fresh, caplog,
                                                               label, kw, word):
    _rebuild(monkeypatch, fresh, **kw)
    got, lines = _warm(caplog)
    assert (got, ae.population_health_word()) == (word, word), label
    assert ae._display_key() not in ae._CACHE[0].live and ae._REBUILDING == [False]
    assert len(lines) == 1 and lines[0].startswith(
        "admin_evidence population warm-up: %s (" % word), lines


def test_a_warm_up_over_the_allowance_reads_budget(monkeypatch, fresh, caplog):
    monkeypatch.setitem(ae.AER_CONTRACT_BOUNDS, "POP_CACHE_MAX_MB", 0)
    _rebuild(monkeypatch, fresh, result=({0: array("d", [1.0])}, {}))
    got, lines = _warm(caplog)
    assert (got, ae.population_health_word()) == ("unavailable:budget",) * 2
    assert len(lines) == 1 and "unavailable:budget (PopulationUnavailable)" in lines[0]


def test_a_database_in_recovery_skips_and_stays_pending(monkeypatch, fresh, caplog):
    async def standby(db):
        return True

    monkeypatch.setattr(ae, "_in_recovery", standby)
    _rebuild(monkeypatch, fresh, result=({0: array("d", [1.0])}, {}))
    got, lines = _warm(caplog)
    assert (got, fresh, ae.population_health_word()) == (None, [], "pending")
    assert len(lines) == 1 and "skipped, the database is in recovery" in lines[0]


def test_a_warm_up_whose_session_fails_logs_and_leaves_the_word(monkeypatch, fresh, caplog):
    class _Down:
        async def __aenter__(self):
            raise OSError("no database")

        async def __aexit__(self, *a):
            return False

    with caplog.at_level(logging.INFO, logger="admin_evidence"):
        got = asyncio.run(ae.warm_display_population(session_factory=_Down, delay_s=0))
    assert (got, ae.population_health_word()) == ("unavailable:error", "pending")


def test_a_report_build_sets_the_word_too(monkeypatch, fresh):
    """Whichever caller makes the attempt: a report's `_leased` records it."""
    _rebuild(monkeypatch, fresh, exc=ae.PopulationUnavailable("p", "duplicate"))
    cache = ae._aer_cache()

    async def go():
        try:
            await ae._leased(cache, None, ae._display_key(), ae._aer_deadline(None))
        except ae.PopulationUnavailable:
            return
        raise AssertionError("published")

    asyncio.run(go())
    assert ae.population_health_word() == "unavailable:duplicate"
    _rebuild(monkeypatch, fresh, result=({0: array("d", [3.0])}, {}))

    async def again():
        g = await ae._leased(cache, None, ae._display_key(), ae._aer_deadline(None))
        cache.release(g)

    asyncio.run(again())
    assert ae.population_health_word() == "ready"


# ── main.py: the start-up task and /health ─────────────────────────────────

import main  # noqa: E402
import schemas  # noqa: E402


def _main_tree():
    with open(main.__file__, encoding="utf-8") as fh:
        return ast.parse(fh.read())


def test_lifespan_creates_the_warm_up_once_on_both_roles_before_it_yields():
    tree = _main_tree()
    (life,) = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)
               and n.name == "lifespan"]
    parents = {}
    for p in ast.walk(life):
        for c in ast.iter_child_nodes(p):
            parents[c] = p
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and ast.unparse(n.func) == "_admin_evidence.warm_display_population"]
    assert len(calls) == 1, [ast.unparse(c) for c in calls]
    (call,) = calls
    assert call in parents, "the warm-up is created outside lifespan"
    outer = parents[call]
    assert ast.unparse(outer) == \
        "asyncio.create_task(_admin_evidence.warm_display_population())"
    append = parents[outer]
    assert ast.unparse(append) == \
        "tasks.append(asyncio.create_task(_admin_evidence.warm_display_population()))"
    node = append
    while node in parents:
        node = parents[node]
        if isinstance(node, ast.If):
            assert "IS_REPLICA" not in ast.unparse(node.test), "created for one role only"
    (yld,) = [n for n in ast.walk(life) if isinstance(n, ast.Yield)]
    assert call.lineno < yld.lineno


class _DownSession:
    async def execute(self, *a, **k):
        raise OSError("popgate: the database is down")

    async def rollback(self):
        pass


def test_both_health_arms_carry_the_two_keys_and_the_schema_requires_them():
    tree = _main_tree()
    (health,) = [n for n in ast.walk(tree)
                 if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"]
    (tried,) = [n for n in ast.walk(health) if isinstance(n, ast.Try)]
    for key, value in (("aer_popgate_build", "_AER_POPGATE_BUILD"),
                       ("admin_evidence_population",
                        "_admin_evidence.population_health_word()")):
        connected = [ast.unparse(k.value) for s in tried.body for k in ast.walk(s)
                     if isinstance(k, ast.keyword) and k.arg == key]
        degraded = [ast.unparse(k.value) for h in tried.handlers for k in ast.walk(h)
                    if isinstance(k, ast.keyword) and k.arg == key]
        assert (connected, degraded) == ([value], [value]), key
        assert len([k for k in ast.walk(tree)
                    if isinstance(k, ast.keyword) and k.arg == key]) == 2, key
    (binding,) = [n for n in tree.body if isinstance(n, ast.Assign)
                  and [ast.unparse(t) for t in n.targets] == ["_AER_POPGATE_BUILD"]]
    assert ast.unparse(binding.value) == "1"
    fields = schemas.HealthResponse.model_fields
    assert fields["aer_popgate_build"].annotation is int
    assert fields["admin_evidence_population"].annotation is str
    assert fields["aer_popgate_build"].is_required()
    assert fields["admin_evidence_population"].is_required()
    answer = asyncio.run(main.health_check(db=_DownSession())).model_dump()
    assert answer["status"] == "degraded" and answer["aer_popgate_build"] == 1, answer
    assert answer["admin_evidence_population"] in ae.POPULATION_WORDS
    for key in ("aer_popgate_build", "admin_evidence_population"):
        partial = dict(answer)
        partial.pop(key)
        with pytest.raises(pydantic.ValidationError):
            schemas.HealthResponse(**partial)
