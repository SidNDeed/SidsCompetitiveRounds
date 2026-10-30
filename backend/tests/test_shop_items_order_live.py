"""/api/v1/shop/items answers the same order from two builds of the same tree.

The route ordered by price alone, and the catalogue has many equal-price rows.
PostgreSQL answers ties in whatever order its sort leaves the heap's rows in,
and an UPDATE writes the row's new version somewhere else in the heap, so two
builds of one tree from one fixture answered different orders (the trunk
oracle's base and control disagreed at /items/1 and /items/10; shop-order-1410).
The route now orders by price, then id.

Two case schemas are built by the read-gate harness. Build B then has every
row whose price another row shares rewritten, highest id first, which is what a
release migration's UPDATE does to a row's place in the heap; the test first
proves that this moved what price ALONE answers (else it could not fail), then
that the route answers both builds identically and in (price, id) order.

READ_GATE_TEST_PG_DSN names the throwaway database (read_gate_pg_harness).
"""
from __future__ import annotations

import pytest

import read_gate_pg_harness as PG
import read_gate_testkit as K
import main

ME = "76561190000004381"           # synthetic
HEADERS_1403 = {"X-Mod-Version": "1.40.3",
                "User-Agent": "UnityPlayer/2019.4.40f1 (UnityWebRequest/1.0, libcurl/7.80.0-DEV)"}
URLS = ("/api/v1/shop/items", "/api/v1/shop/items?steam_id=" + ME)
CATALOGUE = "FROM shop_items WHERE rotation_pool IS NULL AND catalog_ready"


@pytest.fixture(scope="module")
def two_builds():
    PG.require_live_pg()
    lanes = []
    try:
        for prefix in ("shop_order_a", "shop_order_b"):
            lane = PG.Lane(prefix).open()
            lanes.append(lane)
            lane.execute("INSERT INTO players (id, steam_id, display_name) "
                         "VALUES (gen_random_uuid(), $1, 'shop-order') ON CONFLICT DO NOTHING", ME)
        yield lanes
    finally:
        for lane in lanes:
            lane.close()


def _relayout(lane):
    """Rewrite every catalogue row whose price another row shares, highest id
    first, with a no-op SET: each new row version lands after the rows left in
    place. Returns how many rows moved."""
    ids = [r["id"] for r in lane.fetch(
        "SELECT id " + CATALOGUE + " AND price IN (SELECT price " + CATALOGUE +
        " GROUP BY price HAVING count(*) > 1) ORDER BY id DESC")]
    for item_id in ids:
        lane.execute("UPDATE shop_items SET name = name WHERE id = $1", item_id)
    return len(ids)


def _answers(lane, monkeypatch):
    out = []
    with monkeypatch.context() as m:
        m.setenv("API_SECRET_KEY", K.INTERNAL_KEY)
        client = lane.client(m)
        for url in URLS:
            main._RL_BUCKETS.clear()
            r = client.get(url, headers=HEADERS_1403)
            assert r.status_code == 200, (url, r.status_code, r.text[:300])
            out.append([(x["id"], x["price"]) for x in r.json()["items"]])
    return out


def test_two_builds_answer_one_order(two_builds, monkeypatch):
    a, b = two_builds
    assert _relayout(b) > 0, "no catalogue price is shared; the test has nothing to order"
    # The control: on the relaid build, price alone no longer answers id order
    # among ties. If this ever holds, the relayout stopped moving the heap and
    # the assertions below could not fail without the tiebreak.
    price_only = [(r["id"], r["price"]) for r in b.fetch("SELECT id, price " + CATALOGUE + " ORDER BY price")]
    assert price_only != sorted(price_only, key=lambda x: (x[1], x[0])), \
        "the relayout did not move what ORDER BY price answers"
    got_a, got_b = _answers(a, monkeypatch), _answers(b, monkeypatch)
    for url, rows_a, rows_b in zip(URLS, got_a, got_b):
        assert rows_a == rows_b, (url, [(x, y) for x, y in zip(rows_a, rows_b) if x != y][:6])
        keys = [(p, i) for i, p in rows_a]
        assert keys == sorted(keys) and len(set(keys)) == len(keys), url    # (price, id): total
        assert len({p for _, p in rows_a}) < len(rows_a), url              # ties exist to be ordered
