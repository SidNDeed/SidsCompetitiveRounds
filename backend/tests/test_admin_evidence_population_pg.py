"""Admin evidence report, phase 1a item 3: populations, measured.

Live PostgreSQL. A throwaway schema is built from the `Match` model (the
cells module's `Live` helper), so the rebuild statement runs against the
production column set. P9 controls for the game population (design 2.6, 6.1)
and the cache's generation rules:

  * 101 values 0..100 put 50 at mid-rank 0.5;
  * sixty zero ties take the mid-rank (round 10 B1): a 0 among 60 zeros and
    40 ones reads exactly (0 + 0.5 * 60) / 100 = 0.3, a 1 reads 0.8;
  * a dense day of cap+50 values aggregates exactly cap (POP_VALUES_MAX),
    the key truncated, its cutoff the cap-th newest game's ended_at;
  * cap tie: cap-1 newer facts, then one game carrying two seat values for
    one key at the cap; the rebuild with its branches in both orders retains
    identical values, cutoff and rank, keeping the lower subject's fact;
  * sort-key gate: the rebuild plan's row_number sort key ends in the
    subject columns (#606), read by EXPLAIN (VERBOSE);
  * a NULL seat value is no value (never a 0), FLAG keys and unranked keys
    have no population;
  * generations: a publish retires the generation it supersedes and evicts
    its derived results; a leased retired generation stays counted by
    `cache_bytes()` until its last release; a result stored under one
    generation is never returned for another.

Window sources (design 2.6): units newest first, a unit's values newest
first; units with fewer than `n` values excluded; a warm derived result
recomputed after its source expires and a value is added (new `pop_n`,
rank, `computed_at`, provenance equal to the lease). The cache: at most
4 game sets and 8 window sources live; the budget gate waits on a lease
release and refuses at the deadline; `cache_bytes()` within 5% of the
allocations tracemalloc attributes to the module after a window rebuild at
maximum fragmentation.

1a-3N duplicates (round 9 N19), seam family `Z` in this file only: a
fixture table `z_facts` of up to two facts per `(id, subj)` read through
test-only branches put in place of `population_branches` (no production
key or parameter). Per sibling two differently valued facts sharing
`(ki, id, subj)`: the game population at the cap and behind `cap` newer
facts; the player-seat and directional pair-seat window sources in a kept
unit, deeper than WIN_UNIT_DEPTH and in the dropped crossing unit. Each
refuses with `503 unavailable (population)` and one log line, publishes
nothing (the live generation and the gen counter unchanged), and its
one-fact twin serves.

Cold start: `B` measured in a fresh interpreter after the api's imports,
compiled from source with no bytecode cache, then the worst-case cache; `B`
within BASE_RSS_FLOOR_MB, peak x 1.25 within POP_MEM_BUDGET_MB and the worst
case within the budget gate. The gate binds on Linux only (the api
container's resident set); elsewhere the figure is the working set, so the
test reports it and skips with a reason naming the platform.

Present: the two-producer cache-copy observer (:753-801) and route-shape coverage
(test_admin_evidence_routes_pg.py:359-388). Not here yet: route-level cold start (R1-R4, 1a-4).

`ADMIN_EVIDENCE_TEST_PG_DSN` names a database whose name carries
`admin_evidence`; unset, the module fails (an affirmative
`ADMIN_EVIDENCE_TEST_PG_OPTOUT` makes that named skips).
"""

import asyncio
import datetime as dt
import gc
import inspect
import json
import logging
import os
import sys
import time
import tracemalloc
import uuid
import warnings

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import admin_evidence as ae  # noqa: E402
from test_admin_evidence_cells_pg import MATCH_REQUIRED, Live, require_pg  # noqa: E402

HITCH = next(e for e in ae.REPORT_REGISTRY
             if not e.is_window and e.var == "net.hitch50" and e.prov == "SELF")
NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
CAP = ae.CONTRACT_BOUNDS["POP_VALUES_MAX"]


@pytest.fixture()
def live():
    require_pg()
    lv = Live()
    lv.run(lv.up())
    try:
        yield lv
    finally:
        lv.run(lv.down())
        lv.loop.close()


async def _bulk(lv, games):
    """Insert `(p1, p2, ended_at, reporter, cols)` games in one executemany."""
    from sqlalchemy import text
    rows = []
    for p1, p2, ended, rep, cols in games:
        row = dict(MATCH_REQUIRED)
        row.update(id=uuid.uuid4(), player1_id=p1, player2_id=p2, ended_at=ended,
                   reported_by=rep, p1_net_hitch50=None, p2_net_hitch50=None)
        row.update(cols)
        rows.append(row)
    names = sorted(rows[0])
    await lv.conn.execute(text(
        "INSERT INTO matches (%s) VALUES (%s)"
        % (", ".join(names), ", ".join(":%s" % n for n in names))), rows)
    await lv.conn.commit()
    return [r["id"] for r in rows]


def _games(n, start, value_of):
    """`n` games one minute apart from `start`, net.hitch50 on the reporting
    p1 seat, fresh accounts each."""
    out = []
    for i in range(n):
        a, b = uuid.uuid4(), uuid.uuid4()
        out.append((a, b, start + dt.timedelta(minutes=i), a,
                    {"p1_net_hitch50": value_of(i)}))
    return out


async def _rebuild(lv, cap=None):
    return await ae.rebuild_game_population(
        lv.conn, ("display", "all"), pop_days=ae.DISPLAY_DEFAULTS["pop_days"],
        lag_s=ae.DISPLAY_DEFAULTS["lag_s"], cap=cap)


# ── Ranks ──────────────────────────────────────────────────────────────────

def test_p9_mid_rank_of_fifty_among_zero_to_hundred_is_half():
    vals = [float(v) for v in range(101)]
    m = ae.pop_measures(vals, 50.0)
    assert m["pop_rank"] == pytest.approx(0.5) and m["pop_n"] == 101
    assert (m["pop_p50"], m["pop_p90"], m["pop_p99"]) == (50.0, 90.0, 99.0)
    print("GATE p9 mid-rank: 50 among 0..100 = %.4f; p50 %s p90 %s p99 %s"
          % (m["pop_rank"], m["pop_p50"], m["pop_p90"], m["pop_p99"]))


def test_p9_sixty_zero_ties_take_the_mid_rank():
    """B1: zero-inflated, mostly tied counts; the mid-rank stays defined and
    exact where a MAD scale is zero."""
    vals = sorted([0.0] * 60 + [1.0] * 40)
    zero, one = ae.pop_measures(vals, 0.0), ae.pop_measures(vals, 1.0)
    assert zero["pop_rank"] == pytest.approx(0.3)
    assert one["pop_rank"] == pytest.approx(0.8)
    print("GATE p9 sixty zero ties: rank of 0 = %.4f, of 1 = %.4f"
          % (zero["pop_rank"], one["pop_rank"]))


# ── The rebuild statement ──────────────────────────────────────────────────

def test_p9_dense_day_keeps_exactly_cap_and_names_the_cutoff(live):
    start = NOW - dt.timedelta(days=3)

    async def go():
        await _bulk(live, _games(CAP + 50, start, lambda i: i))
        return await _rebuild(live)

    values, truncated = live.run(go())
    vals = values[HITCH.ki]
    assert len(vals) == CAP
    assert list(vals) == [float(v) for v in range(50, CAP + 50)]
    assert truncated[HITCH.ki] == start + dt.timedelta(minutes=50)
    print("GATE p9 dense day: %d of %d values kept, truncated, cutoff %s"
          % (len(vals), CAP + 50, truncated[HITCH.ki].isoformat()))


def test_p9_null_is_no_value_and_unranked_keys_have_no_population(live):
    start = NOW - dt.timedelta(days=2)

    async def go():
        games = _games(3, start, lambda i: (None, 0, 7)[i])
        await _bulk(live, games)
        return await _rebuild(live)

    values, truncated = live.run(go())
    assert list(values[HITCH.ki]) == [0.0, 7.0]
    assert not truncated
    for ki in values:
        e = ae.REPORT_REGISTRY[ki]
        assert e.ranked and not e.is_window, e.key
    print("GATE p9 null: hitch50 population [0.0, 7.0] from values None, 0, 7; "
          "%d keys, all ranked base keys" % len(values))


def _two_seat_branch(ki, seat):
    acc = "g.player1_id" if seat == "p1" else "g.player2_id"
    val = "CAST(g.%s_net_hitch50 AS double precision)" % seat
    return ("SELECT %d AS ki, %s AS val, g.ended_at, g.id, 'seat'::text AS sk, "
            "%s AS sa, CAST(NULL AS uuid) AS sb FROM g WHERE %s IS NOT NULL"
            % (ki, val, acc, val))


def test_p9_cap_tie_is_broken_by_subject_in_both_branch_orders(live, monkeypatch):
    """cap-1 newer facts, then one game whose two seats both carry the key:
    positions cap and cap+1 share ended_at and id and differ only by subject.
    No phase-1 key carries values on both seats of one game, so the tie is
    planted through a test-only branch pair for one ki over both seat columns
    of net.hitch50: the shape a two-seat key (E1, E3, seam family Z) gives the
    statement."""
    start = NOW - dt.timedelta(days=4)
    ki = HITCH.ki
    small = 40
    lo, hi = uuid.UUID(int=1), uuid.UUID(int=2)

    async def go():
        await _bulk(live, [(lo, hi, start, lo, {"p1_net_hitch50": 1000,
                                                "p2_net_hitch50": 2000})])
        await _bulk(live, _games(small - 1, start + dt.timedelta(minutes=1), lambda i: i))
        monkeypatch.setattr(ae, "population_branches", lambda *a, **k: [
            _two_seat_branch(ki, "p1"), _two_seat_branch(ki, "p2")])
        forward = await _rebuild(live, cap=small)
        monkeypatch.setattr(ae, "population_branches", lambda *a, **k: [
            _two_seat_branch(ki, "p2"), _two_seat_branch(ki, "p1")])
        backward = await _rebuild(live, cap=small)
        return forward, backward

    (fv, ft), (bv, bt) = live.run(go())
    assert list(fv[ki]) == list(bv[ki]) and ft == bt
    assert len(fv[ki]) == small and ft[ki] == start
    assert 1000.0 in fv[ki] and 2000.0 not in fv[ki]
    assert ae.pop_measures(fv[ki], 500.0) == ae.pop_measures(bv[ki], 500.0)
    print("GATE p9 cap tie: %d values identical in both branch orders, cutoff %s, "
          "the lower subject's fact kept, rank %.4f"
          % (len(fv[ki]), ft[ki].isoformat(), ae.pop_measures(fv[ki], 500.0)["pop_rank"]))


def _sort_keys(node, out):
    if "Sort Key" in node:
        out.append(list(node["Sort Key"]))
    for child in node.get("Plans", []):
        _sort_keys(child, out)
    return out


def test_p9_rebuild_sort_key_ends_in_the_subject(live):
    """#606: the row_number order that picks the newest `cap` facts breaks a
    tie on the fact's subject identity, read from the plan itself."""
    from sqlalchemy import text

    async def go():
        sql = ae.population_sql(ae.population_branches())
        res = await live.conn.execute(
            text("EXPLAIN (VERBOSE, FORMAT JSON) " + sql),
            {"pop_days": 30, "lag_s": 120, "cap": CAP})
        raw = res.scalar()
        doc = json.loads(raw) if isinstance(raw, str) else raw
        return doc[0]["Plan"]

    plan = live.run(go())
    keys = [k for k in _sort_keys(plan, []) if any("ended_at DESC" in s for s in k)]
    assert keys, "no sort over ended_at DESC in the rebuild plan"
    for k in keys:
        assert [s.split(".")[-1] for s in k[-5:]] == [
            "ended_at DESC", "id DESC", "sk", "sa", "sb"], k
    print("GATE p9 sort key: %s" % keys[0])


# ── Generations, leases, memo ──────────────────────────────────────────────

class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _arr(*v):
    from array import array
    return array("d", v)


def test_p9_publish_retires_the_old_generation_and_its_derived_results():
    clock = _Clock()
    cache = ae.PopulationCache(clock=clock)
    key = ("display", "all", ae.registry_fingerprint(), 30, 120)
    g1 = cache.publish(key, {HITCH.ki: _arr(1, 2, 3)}, {})
    lease = cache.lease(g1)
    comp = ("w", "player", 3)
    cache.memo_put(comp, lease, {"pop_rank": 0.5}, 64)
    assert cache.memo_get(comp, lease)["gen"] == g1.gen
    before = cache.cache_bytes()
    clock.t += 1
    g2 = cache.publish(key, {HITCH.ki: _arr(1, 2, 3, 4)}, {})
    assert g2.gen > g1.gen and g2.computed_at > g1.computed_at
    assert cache.current(key) is g2
    assert g1.retired and g1 in cache.retired
    assert cache.memo_get(comp, lease) is None and cache.memo_bytes == 0
    assert cache.cache_bytes() == g1.nbytes() + g2.nbytes()
    cache.release(g1)
    assert g1 not in cache.retired and cache.cache_bytes() == g2.nbytes()
    clock.t += ae.CONTRACT_BOUNDS["POP_TTL_S"]
    assert cache.current(key) is None
    print("GATE p9 generations: gen %d retired under its lease (%d bytes counted, "
          "then %d), derived result evicted, gen %d expires at POP_TTL_S"
          % (g1.gen, before, cache.cache_bytes(), g2.gen))


def test_p9_a_result_is_never_returned_for_another_generation():
    cache = ae.PopulationCache(clock=_Clock())
    a = cache.publish(("display", "all"), {HITCH.ki: _arr(1)}, {})
    b = cache.publish(("display", "ranked"), {HITCH.ki: _arr(2)}, {})
    comp = ("w", "pair", 2)
    cache.memo_put(comp, a, {"pop_rank": 0.25}, 32)
    assert cache.memo_get(comp, b) is None
    stored = cache.memo_get(comp, a)
    assert (stored["source_key"], stored["gen"], stored["computed_at"]) == (
        a.key, a.gen, a.computed_at)
    print("GATE p9 relabel: a result stored under gen %d is not served to gen %d"
          % (a.gen, b.gen))


def test_p9_a_result_is_served_only_to_its_own_provenance():
    """A lease naming the same source key and gen but another computed_at is
    not the result's provenance: the result is recomputed, never relabelled."""
    cache = ae.PopulationCache(clock=_Clock())
    a = cache.publish(("display", "all"), {HITCH.ki: _arr(1)}, {})
    comp = ("w", "player", 1)
    cache.memo_put(comp, a, {"pop_rank": 0.5}, 32)
    other = ae.Generation(key=a.key, gen=a.gen, computed_at=a.computed_at + 1,
                          values={}, truncated={})
    assert cache.memo_get(comp, other) is None
    assert cache.memo_get(comp, a)["computed_at"] == a.computed_at
    print("GATE p9 provenance: same key and gen, computed_at %s against %s: recomputed"
          % (other.computed_at, a.computed_at))


def test_p9_live_generations_stay_within_four_game_sets_and_eight_window_sources():
    cache = ae.PopulationCache(clock=_Clock())
    games = [cache.publish(("display", "all", "fp", 30, i), {HITCH.ki: _arr(i)}, {})
             for i in range(5)]
    windows = [cache.publish(("display", "all", "fp", 30, i, "player"), {HITCH.ki: _arr(i)},
                             {}, offsets={HITCH.ki: ae.array("i", [0, 1])})
               for i in range(9)]
    live = list(cache.live.values())
    assert sum(g.kind == "game" for g in live) == ae.CONTRACT_BOUNDS["GAME_SETS_LIVE"]
    assert sum(g.kind == "window" for g in live) == ae.CONTRACT_BOUNDS["WINDOW_SOURCES_LIVE"]
    assert games[0].retired and windows[0].retired
    assert not games[1].retired and not windows[1].retired
    print("GATE p9 live caps: %d game sets, %d window sources live; the oldest of each retired"
          % (sum(g.kind == "game" for g in live), sum(g.kind == "window" for g in live)))


# ── Window sources ─────────────────────────────────────────────────────────

MEDIAN_OF_HITCH = next(e for e in ae.REPORT_REGISTRY
                       if e.is_window and e.base == HITCH.ki and e.agg.startswith("win_median"))


async def _hitch_pairs(lv, start):
    """X (p1, reporting) plays Y three games (values 1, 2, 3) then Z two
    games (10, 20), one minute apart."""
    x, y, z = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    games = [(x, y, start + dt.timedelta(minutes=i), x, {"p1_net_hitch50": v})
             for i, v in enumerate((1, 2, 3))]
    games += [(x, z, start + dt.timedelta(minutes=3 + i), x, {"p1_net_hitch50": v})
              for i, v in enumerate((10, 20))]
    await _bulk(lv, games)
    return x


def test_p9_window_source_units_newest_first_and_units_need_n_values(live):
    start = NOW - dt.timedelta(days=6)
    ki = HITCH.ki

    async def go():
        await _hitch_pairs(live, start)
        out = {}
        for basis in ("player", "pair"):
            out[basis] = await ae.rebuild_window_source(
                live.conn, ("display", "all", basis), basis, 30, 120)
        return out

    out = live.run(go())
    pv, po, pt = out["player"]
    assert list(pv[ki]) == [20.0, 10.0, 3.0, 2.0, 1.0] and list(po[ki]) == [0, 5]
    qv, qo, qt = out["pair"]
    assert list(qv[ki]) == [20.0, 10.0, 3.0, 2.0, 1.0] and list(qo[ki]) == [0, 2, 5]
    assert ki not in pt and ki not in qt
    assert list(ae.window_population(qv[ki], qo[ki], "win_median", 2)) == [2.5, 15.0]
    assert list(ae.window_population(qv[ki], qo[ki], "win_median", 3)) == [2.0]
    assert list(ae.window_population(qv[ki], qo[ki], "win_max", 2)) == [3.0, 20.0]
    assert list(ae.window_population(pv[ki], po[ki], "win_median", 5)) == [3.0]
    assert list(ae.window_population(pv[ki], po[ki], "win_median", 6)) == []
    print("GATE p9 window units: player offsets %s, pair offsets %s; pair medians at n=2 "
          "[2.5, 15.0], at n=3 [2.0]; player at n=6 none"
          % (list(po[ki]), list(qo[ki])))


def test_p9_generation_a_warm_result_is_recomputed_after_its_source_expires(live):
    start = NOW - dt.timedelta(days=7)
    ki = HITCH.ki
    clock = _Clock()
    cache = ae.PopulationCache(clock=clock)
    key = ("display", "all", ae.registry_fingerprint(), 30, 120, "pair")
    comp = ae.comparability_key(MEDIAN_OF_HITCH.key, "pair", 2)

    async def go():
        x = await _hitch_pairs(live, start)
        g1 = await ae.refresh_window_source(cache, live.conn, key, "pair", 30, 120)
        lease = cache.lease(g1)
        dist = ae.window_population(g1.values[ki], g1.offsets[ki], "win_median", 2)
        r1 = dict(cache.memo_put(comp, lease, ae.pop_measures(dist, 15.0), 64))
        clock.t += ae.CONTRACT_BOUNDS["POP_TTL_S"] - 1
        warm = cache.current(key) is g1 and cache.memo_get(comp, lease) is not None
        cache.release(lease)
        w = uuid.uuid4()
        await _bulk(live, [(x, w, start + dt.timedelta(minutes=5 + i), x,
                            {"p1_net_hitch50": v}) for i, v in enumerate((30, 40))])
        clock.t += 2
        expired = cache.current(key) is None
        g2 = await ae.refresh_window_source(cache, live.conn, key, "pair", 30, 120)
        lease2 = cache.lease(g2)
        stale = cache.memo_get(comp, lease2)
        dist2 = ae.window_population(g2.values[ki], g2.offsets[ki], "win_median", 2)
        r2 = cache.memo_put(comp, lease2, ae.pop_measures(dist2, 15.0), 64)
        cache.release(lease2)
        return g1, g2, r1, r2, warm, expired, stale

    g1, g2, r1, r2, warm, expired, stale = live.run(go())
    assert warm and expired and stale is None
    assert g2.gen > g1.gen and g2.computed_at > g1.computed_at
    assert (r1["pop_n"], r2["pop_n"]) == (2, 3)
    assert (r1["pop_rank"], r2["pop_rank"]) == (pytest.approx(0.75), pytest.approx(0.5))
    assert (r2["source_key"], r2["gen"], r2["computed_at"]) == (g2.key, g2.gen, g2.computed_at)
    assert (r1["source_key"], r1["gen"], r1["computed_at"]) == (g1.key, g1.gen, g1.computed_at)
    assert all(mk[2] != g1.gen for mk in cache.memo)
    print("GATE p9 generation: gen %d -> %d, pop_n 2 -> 3, rank 0.75 -> 0.50, "
          "computed_at %s -> %s, provenance equal to the lease"
          % (g1.gen, g2.gen, r1["computed_at"], r2["computed_at"]))


# ── Budget gate and byte count ─────────────────────────────────────────────

def _big(n_bytes):
    from array import array
    return array("d", bytes(n_bytes))


def _gate_cache(budget_mb):
    """A cache whose budget is `budget_mb`: B set so POP_MEM_BUDGET_MB/1.25 - B - 2 = it."""
    b = ae.CONTRACT_BOUNDS["POP_MEM_BUDGET_MB"] / 1.25 - 2 - budget_mb
    return ae.PopulationCache(clock=_Clock(), base_rss_mb=b)


def test_p9_budget_gate_waits_on_a_lease_release():
    cache = _gate_cache(1.5)
    key = ("display", "all", "fp", 30, 120)
    part = 600 * 1024

    async def go():
        g1 = await ae._admit_and_publish(cache, key, {1: _big(part)}, {}, None,
                                         time.monotonic(), None)
        lease = cache.lease(g1)
        g2 = await ae._admit_and_publish(cache, key, {1: _big(part)}, {}, None,
                                         time.monotonic(), None)
        assert g1.retired and g1 in cache.retired

        async def later():
            await asyncio.sleep(0.3)
            cache.release(lease)

        t0 = time.monotonic()
        task = asyncio.ensure_future(later())
        g3 = await ae._admit_and_publish(cache, key, {1: _big(part)}, {}, None,
                                         t0, t0 + 5)
        waited = time.monotonic() - t0
        await task
        return g2, g3, waited

    loop = asyncio.new_event_loop()
    try:
        g2, g3, waited = loop.run_until_complete(go())
    finally:
        loop.close()
    assert waited >= 0.25, "published after %.3f s, before the lease was released" % waited
    assert cache.current(key) is g3 and g2.retired
    print("GATE p9 budget wait: budget %d bytes, third %d-byte publish admitted after "
          "%.3f s, at the lease release" % (cache.budget, part, waited))


def test_p9_budget_gate_refuses_at_the_deadline(caplog):
    cache = _gate_cache(1.5)
    key = ("display", "all", "fp", 30, 120)
    part = 600 * 1024

    async def go():
        g1 = await ae._admit_and_publish(cache, key, {1: _big(part)}, {}, None,
                                         time.monotonic(), None)
        cache.lease(g1)
        g2 = await ae._admit_and_publish(cache, key, {1: _big(part)}, {}, None,
                                         time.monotonic(), None)
        t0 = time.monotonic()
        try:
            await ae._admit_and_publish(cache, key, {1: _big(part)}, {}, None, t0, t0 + 0.3)
        except ae.PopulationUnavailable as exc:
            return g2, exc
        return g2, None

    loop = asyncio.new_event_loop()
    try:
        with caplog.at_level(logging.WARNING, logger="admin_evidence"):
            g2, exc = loop.run_until_complete(go())
    finally:
        loop.close()
    assert exc is not None, "a replacement over the budget published"
    assert (exc.status, exc.detail) == (503, "unavailable (population)")
    assert cache.current(key) is g2 and cache.in_progress == 0
    assert [r for r in caplog.records if "population unavailable" in r.getMessage()]
    print("GATE p9 budget refusal: %s" % exc)


# ── Seam family Z (test builds only) ───────────────────────────────────────

Z_KI = 10000          # a test-only key number, outside the registry


def _z_branches(entries=None, partner=False, kis=(Z_KI,)):
    po = (", CASE z.seat WHEN 'p1' THEN g.player2_id ELSE g.player1_id END AS po"
          if partner else "")
    return ["SELECT z.ki, z.val, g.ended_at, g.id, 'seat'::text AS sk, "
            "CASE z.seat WHEN 'p1' THEN g.player1_id ELSE g.player2_id END AS sa, "
            "CAST(NULL AS uuid) AS sb%s FROM g JOIN z_facts z ON z.match_id = g.id "
            "WHERE z.ki = %d AND z.val IS NOT NULL" % (po, k) for k in kis]


async def _z_table(lv):
    from sqlalchemy import text
    await lv.conn.execute(text(
        "CREATE TABLE z_facts (match_id uuid NOT NULL, seat text NOT NULL, "
        "ki integer NOT NULL, val double precision)"))
    await lv.conn.commit()


async def _z_facts(lv, facts):
    """`(match_id, seat, ki, val)` facts; up to two per `(id, subj)`."""
    from sqlalchemy import text
    await lv.conn.execute(text(
        "INSERT INTO z_facts (match_id, seat, ki, val) VALUES (:m, :s, :k, :v)"),
        [{"m": m, "s": s, "k": k, "v": v} for m, s, k, v in facts])
    await lv.conn.commit()


def _refused(records):
    return [r for r in records if "admin_evidence population unavailable" in r.getMessage()]


@pytest.mark.parametrize("placement", ["at_cap", "behind_cap"])
def test_p9_duplicate_game_population_refuses(live, monkeypatch, caplog, placement):
    monkeypatch.setattr(ae, "population_branches", _z_branches)
    small = 40
    newer = small - 1 if placement == "at_cap" else small
    start = NOW - dt.timedelta(days=8)
    clock = _Clock()
    cache = ae.PopulationCache(clock=clock)
    key = ("display", "all", "z", 30, 120)

    async def go():
        await _z_table(live)
        a, b = uuid.uuid4(), uuid.uuid4()
        [dup] = await _bulk(live, [(a, b, start, a, {})])
        ids = await _bulk(live, _games(newer, start + dt.timedelta(minutes=1), lambda i: None))
        await _z_facts(live, [(m, "p1", Z_KI, float(i)) for i, m in enumerate(ids)]
                       + [(dup, "p1", Z_KI, 500.0)])
        twin = await ae.refresh_game_set(cache, live.conn, key, 30, 120, cap=small)
        await _z_facts(live, [(dup, "p1", Z_KI, 501.0)])
        clock.t += ae.CONTRACT_BOUNDS["POP_TTL_S"]
        try:
            await ae.refresh_game_set(cache, live.conn, key, 30, 120, cap=small)
        except ae.PopulationUnavailable as exc:
            return twin, exc
        return twin, None

    with caplog.at_level(logging.WARNING, logger="admin_evidence"):
        twin, exc = live.run(go())
    assert len(twin.values[Z_KI]) == small
    assert (500.0 in twin.values[Z_KI]) == (placement == "at_cap")
    assert exc is not None, "the duplicate %s did not refuse" % placement
    assert (exc.status, exc.detail) == (503, "unavailable (population)")
    assert len(_refused(caplog.records)) == 1
    assert cache.live[key] is twin and cache._gen == twin.gen and not twin.retired
    print("GATE p9 duplicate game %s: twin gen %d served %d values; duplicate refused: %s"
          % (placement, twin.gen, len(twin.values[Z_KI]), exc))


# Units for the window placements, newest unit first: U1 35 games (30 kept
# by depth), U2 10 games (kept, 40 values), U3 5 games (crosses 40: dropped).
_WINDOW_PLACEMENT = {"kept": (0, 34), "deep": (0, 2), "crossing": (2, 4)}


@pytest.mark.parametrize("placement", ["kept", "deep", "crossing"])
@pytest.mark.parametrize("basis", ["player", "pair"])
def test_p9_duplicate_window_source_refuses(live, monkeypatch, caplog, basis, placement):
    monkeypatch.setattr(ae, "population_branches", _z_branches)
    start = NOW - dt.timedelta(days=9)
    clock = _Clock()
    cache = ae.PopulationCache(clock=clock)
    key = ("display", "all", "z", 30, 120, basis)
    wmax = 40

    async def go():
        await _z_table(live)
        units = []
        for u, (count, base) in enumerate(((35, 100), (10, 50), (5, 0))):
            a, b = uuid.uuid4(), uuid.uuid4()
            units.append(await _bulk(live, [
                (a, b, start + dt.timedelta(minutes=base + i), a, {}) for i in range(count)]))
        await _z_facts(live, [(m, "p1", Z_KI, float(100 * u + i))
                              for u, ids in enumerate(units) for i, m in enumerate(ids)])
        twin = await ae.refresh_window_source(cache, live.conn, key, basis, 30, 120,
                                              wmax=wmax)
        u, i = _WINDOW_PLACEMENT[placement]
        await _z_facts(live, [(units[u][i], "p1", Z_KI, 100 * u + i + 0.5)])
        clock.t += ae.CONTRACT_BOUNDS["POP_TTL_S"]
        try:
            await ae.refresh_window_source(cache, live.conn, key, basis, 30, 120, wmax=wmax)
        except ae.PopulationUnavailable as exc:
            return twin, exc
        return twin, None

    with caplog.at_level(logging.WARNING, logger="admin_evidence"):
        twin, exc = live.run(go())
    assert list(twin.offsets[Z_KI]) == [0, 30, 40] and Z_KI in twin.truncated
    assert list(twin.values[Z_KI][:3]) == [34.0, 33.0, 32.0]
    assert exc is not None, "the duplicate %s (%s) did not refuse" % (placement, basis)
    assert (exc.status, exc.detail) == (503, "unavailable (population)")
    assert len(_refused(caplog.records)) == 1
    assert cache.live[key] is twin and cache._gen == twin.gen and not twin.retired
    print("GATE p9 duplicate window %s %s: twin gen %d served offsets %s; refused: %s"
          % (basis, placement, twin.gen, list(twin.offsets[Z_KI]), exc))


_COLD_START = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import main                      # the api's own imports (design 2.6: main.py)
import admin_evidence as ae
from array import array
b = ae.process_rss_mb()
P = ae.CONTRACT_BOUNDS["POP_VALUES_MAX"]
W = ae.CONTRACT_BOUNDS["WIN_VALUES_MAX"]
R = sum(1 for e in ae.REPORT_REGISTRY if not e.is_window and e.ranked)
cache = ae.PopulationCache(base_rss_mb=b)
def vals(n):
    return {k: array("d", bytes(8 * n)) for k in range(R)}
def offs(n):
    return {k: array("i", bytes(4 * (n + 1))) for k in range(R)}
for i in range(4):               # 4 live game sets, 4 retired under leases
    cache.lease(cache.publish(("g", i), vals(P), {}))
    cache.publish(("g", i), vals(P), {})
replacement = vals(P)            # 1 replacement in progress
cache.in_progress = sum(len(a) * 8 for a in replacement.values())
for i in range(8):               # 8 live window sources, 4 retired, one value per unit
    if i < 4:
        cache.lease(cache.publish(("w", i), vals(W), {}, offsets=offs(W)))
    cache.publish(("w", i), vals(W), {}, offsets=offs(W))
lease = cache.current(("w", 0))
for j in range(32):              # the memo at WIN_DERIVED_BYTES_MAX
    cache.memo_put(("c", j), lease, {"d": array("d", bytes(65536))}, 65536)
print(json.dumps({"b": b, "peak": ae.process_rss_mb(peak=True), "platform": sys.platform,
                  "python": sys.version.split()[0], "cache_bytes": cache.cache_bytes(), "budget": cache.budget,
                  "live": len(cache.live), "retired": len(cache.retired),
                  "pycache_prefix": sys.pycache_prefix, "dont_write": sys.dont_write_bytecode}))
"""

# The marker every off-Linux run of the cold-start gate carries in its skip
# reason, so the skip is visible in a summary and countable by a reader.
P9_OFF_LINUX = "P9-OFF-LINUX"


def test_p9_cold_start_base_rss_and_peak_within_the_budget():
    """Cold start (design 2.6, P9): `B` is the resident set after the api's
    imports, measured in a fresh interpreter; then the cache at its worst
    case (4 live and 4 leased-retired game sets, a replacement, 8 live and 4
    retired window sources at maximum fragmentation, the memo full). `B`
    must not exceed BASE_RSS_FLOOR_MB, peak x 1.25 must fit
    POP_MEM_BUDGET_MB, and the worst-case cache must fit the budget gate at
    the measured `B`.

    The bytecode cache is an input of `B` (one Linux seat, one tree: 160.4
    MB alone, 102.7 MB in a run whose earlier tests had imported the api;
    on win32 a compiled copy of backend/api measured 109.5 against 114.5
    uncompiled, peak 126 against 164), so the fresh interpreter runs with -B and
    PYTHONPYCACHEPREFIX naming a new empty directory: it reads no tree's
    __pycache__ and writes nothing, and every module compiles from source,
    as the api container's first start does. The test proves that state
    from the child (the prefix it saw, bytecode writing off) and from the
    directory (still empty after the run).

    The gate binds on Linux only, where the figure is the api container's
    resident set. On any other platform the figure is that platform's
    working set (win32 measured about 114 MB compiled cold), which the
    design's bounds do not describe; the test runs the same measurement and
    the same state checks, then skips with a reason that starts with
    P9_OFF_LINUX and names the platform and the measured line. The
    measured line is also issued as a warning, so a quiet run (`-q`, no
    captured output shown) still prints the figure on every outcome. This
    test reads no database, so it runs without the DSN."""
    import shutil
    import subprocess
    import tempfile
    api = os.path.join(HERE, "..", "api")
    prefix = tempfile.mkdtemp(prefix="p9-pycache-")
    env = dict(os.environ, PYTHONPYCACHEPREFIX=prefix)
    try:
        out = subprocess.run([sys.executable, "-B", "-c", _COLD_START, api],
                             capture_output=True, text=True, timeout=300, env=env)
        left = sorted(os.listdir(prefix))
    finally:
        shutil.rmtree(prefix, ignore_errors=True)
    assert out.returncode == 0, out.stderr[-2000:]
    m = json.loads(out.stdout.strip().splitlines()[-1])
    assert os.path.normcase(os.path.abspath(m["pycache_prefix"] or "")) == \
        os.path.normcase(os.path.abspath(prefix)), m
    assert m["dont_write"] is True, m
    assert left == [], "the cold interpreter wrote bytecode: %s" % left[:5]
    line = ("GATE p9 cold start (%s, Python %s): B %.1f MB (floor %.1f), peak %.1f MB "
            "x 1.25 = %.1f (budget %d), cache %d bytes against %d, %d live, %d retired"
            % (m["platform"], m["python"], m["b"], ae.BASE_RSS_FLOOR_MB, m["peak"],
               m["peak"] * 1.25, ae.CONTRACT_BOUNDS["POP_MEM_BUDGET_MB"], m["cache_bytes"],
               m["budget"], m["live"], m["retired"]))
    print(line)
    warnings.warn(line)
    assert (m["live"], m["retired"]) == (12, 8)
    if sys.platform != "linux":
        pytest.skip("%s platform=%s: the cold-start gate binds on Linux only (the api "
                    "container's resident set); this figure is the %s working set, "
                    "reported, not gated: %s" % (P9_OFF_LINUX, sys.platform, sys.platform, line))
    assert m["b"] <= ae.BASE_RSS_FLOOR_MB, "B %.1f MB misses the floor: a budget decision" % m["b"]
    assert m["peak"] * 1.25 <= ae.CONTRACT_BOUNDS["POP_MEM_BUDGET_MB"], m
    assert m["cache_bytes"] <= m["budget"], "the worst-case cache misses the budget gate: %s" % m


def _builder_lines():
    """Line spans of the SQL text builders: a statement string the driver's
    compiled cache keeps is no part of the population's bytes."""
    spans = []
    for fn in (ae.window_source_sql, ae.population_sql, ae._window_cte,
               ae.population_branches):
        src, first = inspect.getsourcelines(fn)
        spans.append((first, first + len(src)))
    return spans


def test_p9_cache_bytes_within_five_percent_of_tracemalloc(live, monkeypatch):
    """A game set and a window source at maximum fragmentation (one value per
    unit, eight keys): the bytes `cache_bytes()` counts are within 5% of what
    tracemalloc attributes to allocations made in admin_evidence.py and held."""
    kis = tuple(range(Z_KI, Z_KI + 8))
    monkeypatch.setattr(ae, "population_branches",
                        lambda entries=None, partner=False: _z_branches(partner=partner, kis=kis))
    start = NOW - dt.timedelta(days=10)
    units = ae.CONTRACT_BOUNDS["WIN_VALUES_MAX"]
    cache = ae.PopulationCache(clock=_Clock())
    game_key = ("display", "all", "z", 30, 120)
    window_key = game_key + ("pair",)
    # The file name tracemalloc records is the code object's own: the module is
    # imported through a sys.path entry holding "..", which abspath would
    # normalize away and then match nothing.
    path = ae.rebuild_window_source.__code__.co_filename

    async def go():
        await _z_table(live)
        games = [(uuid.uuid4(), uuid.uuid4(), start + dt.timedelta(seconds=i), None, {})
                 for i in range(units)]
        games = [(p1, p2, ended, p1, cols) for p1, p2, ended, _r, cols in games]
        ids = await _bulk(live, games)
        await _z_facts(live, [(m, "p1", k, float(i)) for i, m in enumerate(ids) for k in kis])
        gc.collect()
        tracemalloc.start(1)
        try:
            game = await ae.refresh_game_set(cache, live.conn, game_key, 30, 120)
            window = await ae.refresh_window_source(
                cache, live.conn, window_key, "pair", 30, 120)
            gc.collect()
            snap = tracemalloc.take_snapshot()
        finally:
            tracemalloc.stop()
        return game, window, snap

    game, window, snap = live.run(go())
    spans = _builder_lines()
    held = 0
    for stat in snap.filter_traces([tracemalloc.Filter(True, path)]).statistics("lineno"):
        line = stat.traceback[0].lineno
        if not any(lo <= line < hi for lo, hi in spans):
            held += stat.size
    counted = cache.cache_bytes()
    assert len(game.values) == len(kis) and all(len(game.values[k]) == units for k in kis)
    assert len(window.values) == len(kis) and all(
        len(window.values[k]) == units and len(window.offsets[k]) == units + 1 for k in kis)
    assert counted == game.nbytes() + window.nbytes()
    assert abs(held - counted) <= 0.05 * held, (held, counted)
    print("GATE p9 bytes: cache_bytes %d, tracemalloc held at module lines %d (%.2f%%)"
          % (counted, held, 100.0 * abs(held - counted) / held))
