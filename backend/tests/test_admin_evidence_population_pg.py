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

Not here yet (item 1a-3, later passes): window sources, the budget gate,
cold-start B, tracemalloc and RSS measures, and the 1a-3N duplicates.

`ADMIN_EVIDENCE_TEST_PG_DSN` names a database whose name carries
`admin_evidence`; unset, the module fails (an affirmative
`ADMIN_EVIDENCE_TEST_PG_OPTOUT` makes that named skips).
"""

import datetime as dt
import json
import os
import sys
import uuid

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


def _games(n, start, value_of):
    """`n` games one minute apart from `start`, net.hitch50 on the reporting
    p1 seat, fresh accounts each."""
    out = []
    for i in range(n):
        a, b = uuid.uuid4(), uuid.uuid4()
        out.append((a, b, start + dt.timedelta(minutes=i), a,
                    {"p1_net_hitch50": value_of(i)}))
    return out


async def _rebuild(lv, cap=None, branches=None):
    return await ae.rebuild_game_population(
        lv.conn, ("display", "all"), pop_days=ae.DISPLAY_DEFAULTS["pop_days"],
        lag_s=ae.DISPLAY_DEFAULTS["lag_s"], cap=cap, branches=branches)


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


def test_p9_cap_tie_is_broken_by_subject_in_both_branch_orders(live):
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
        forward = await _rebuild(live, cap=small,
                                 branches=[_two_seat_branch(ki, "p1"),
                                           _two_seat_branch(ki, "p2")])
        backward = await _rebuild(live, cap=small,
                                  branches=[_two_seat_branch(ki, "p2"),
                                            _two_seat_branch(ki, "p1")])
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
