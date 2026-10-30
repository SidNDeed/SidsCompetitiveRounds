"""/api/v1/shop/items answers equal prices in id order, on both of its paths.

The route ordered by price alone, and the catalogue has many equal-price rows.
PostgreSQL answers ties in whatever order its sort leaves the heap's rows, and
an UPDATE writes a row's new version wherever its page has room, so two builds
of one tree from one fixture answered different orders (the trunk oracle's base
and control disagreed at /items/1 and /items/10; shop-order-1410). Both of the
route's shop_items reads now order by price, then id: the catalogue, and the
owned achievement rows it appends after the catalogue.

Nothing here needs the heap to produce a non-canonical order:

* the CONTRACT: every statement the route sends is captured
  (before_cursor_execute), and each of its two shop_items SELECTs must end in
  ORDER BY price, id. This holds on every run of a correct tree and fails on
  every run of a tree missing either tiebreak;
* the BEHAVIOUR, which is always true on a correct tree: the fixture player
  OWNS several equal-price achievement items (granted highest id first), and
  the answer is the catalogue in (price, id) order followed by exactly those
  owned rows in (price, id) order; and two builds of the same tree (the second
  with its equal-price rows rewritten highest id first, as a release
  migration's UPDATE would) answer the same order.

READ_GATE_TEST_PG_DSN names the throwaway database (read_gate_pg_harness).
"""
from __future__ import annotations

import re

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

import read_gate_pg_harness as PG
import read_gate_testkit as K
import main

ME = "76561190000004381"           # synthetic
HEADERS_1403 = {"X-Mod-Version": "1.40.3",
                "User-Agent": "UnityPlayer/2019.4.40f1 (UnityWebRequest/1.0, libcurl/7.80.0-DEV)"}
URL_ANON = "/api/v1/shop/items"
URL_ME = "/api/v1/shop/items?steam_id=" + ME
CATALOGUE = "FROM shop_items WHERE rotation_pool IS NULL AND catalog_ready"
OWNED_ACHIEVEMENTS = 4
# the route's two shop_items reads, told apart by their pool predicate
READS = {"catalogue": re.compile(r"shop_items\.rotation_pool IS NULL", re.I),
         "achievement": re.compile(r"shop_items\.rotation_pool = ", re.I)}
TIEBREAK = re.compile(r"ORDER BY shop_items\.price, shop_items\.id\s*$", re.I)


@pytest.fixture(scope="module")
def two_builds():
    PG.require_live_pg()
    lanes = []
    try:
        for prefix in ("shop_order_a", "shop_order_b"):
            lane = PG.Lane(prefix).open()
            lanes.append(lane)
            _own_achievements(lane)
        yield lanes
    finally:
        for lane in lanes:
            lane.close()


def _own_achievements(lane):
    """The fixture player owns OWNED_ACHIEVEMENTS achievement items that share
    one price (the most common one), granted highest id first. Kinds the
    version gates drop for 1.40.3 (dances, music) are left out so every grant
    is answered. Returns the owned ids."""
    lane.execute("INSERT INTO players (id, steam_id, display_name) "
                 "VALUES (gen_random_uuid(), $1, 'shop-order') ON CONFLICT DO NOTHING", ME)
    rows = lane.fetch(
        "SELECT id FROM shop_items WHERE rotation_pool = 'achievement' AND kind NOT IN ('dance', 'music_album') "
        "AND price = (SELECT price FROM shop_items WHERE rotation_pool = 'achievement' "
        "             GROUP BY price ORDER BY count(*) DESC, price LIMIT 1) "
        "ORDER BY id DESC LIMIT $1", OWNED_ACHIEVEMENTS)
    ids = [r["id"] for r in rows]
    assert len(ids) == OWNED_ACHIEVEMENTS, ("the build has too few equal-price achievement items", ids)
    for item_id in ids:
        lane.execute("INSERT INTO player_items (player_id, item_id, purchased_at, purchase_price) "
                     "SELECT p.id, $2, now(), 0 FROM players p WHERE p.steam_id = $1 ON CONFLICT DO NOTHING",
                     ME, item_id)
    return ids


def _relayout(lane):
    """Rewrite every shop row whose price another row of its pool shares,
    highest id first, with a no-op SET (a release migration's UPDATE moves a
    row the same way). Returns how many rows were rewritten."""
    ids = [r["id"] for r in lane.fetch(
        "SELECT id FROM shop_items s WHERE (SELECT count(*) FROM shop_items t WHERE t.price = s.price "
        "AND t.rotation_pool IS NOT DISTINCT FROM s.rotation_pool) > 1 ORDER BY id DESC")]
    for item_id in ids:
        lane.execute("UPDATE shop_items SET name = name WHERE id = $1", item_id)
    return len(ids)


def _answers(lane, monkeypatch):
    """{url: [(id, price)]} and every statement the route sent, per url."""
    out, sent = {}, {}
    with monkeypatch.context() as m:
        m.setenv("API_SECRET_KEY", K.INTERNAL_KEY)
        client = lane.client(m)
        for url in (URL_ANON, URL_ME):
            seen = []

            def _capture(conn, cursor, statement, parameters, context, executemany):
                seen.append(statement)
            event.listen(Engine, "before_cursor_execute", _capture)
            try:
                main._RL_BUCKETS.clear()
                r = client.get(url, headers=HEADERS_1403)
            finally:
                event.remove(Engine, "before_cursor_execute", _capture)
            assert r.status_code == 200, (url, r.status_code, r.text[:300])
            out[url] = [(x["id"], x["price"]) for x in r.json()["items"]]
            sent[url] = seen
    return out, sent


def _shop_reads(statements):
    """{"catalogue"|"achievement": [statement]} for the SELECTs from shop_items."""
    reads = {k: [] for k in READS}
    for s in statements:
        flat = " ".join(s.split())
        if not re.match(r"SELECT .* FROM shop_items\b", flat, re.I):
            continue
        for name, pattern in READS.items():
            if pattern.search(flat):
                reads[name].append(flat)
    return reads


def test_both_reads_order_by_price_then_id(two_builds, monkeypatch):
    """The contract, deterministic: each shop_items read the route sends ends
    in ORDER BY price, id. The steam_id request owns achievements, so it sends
    both reads; the anonymous one sends only the catalogue read."""
    a, _ = two_builds
    _, sent = _answers(a, monkeypatch)
    me, anon = _shop_reads(sent[URL_ME]), _shop_reads(sent[URL_ANON])
    assert len(me["catalogue"]) == 1 and len(me["achievement"]) == 1, me
    assert len(anon["catalogue"]) == 1 and anon["achievement"] == [], anon
    for name, stmt in (("catalogue", me["catalogue"][0]), ("achievement", me["achievement"][0]),
                       ("catalogue (anonymous)", anon["catalogue"][0])):
        assert TIEBREAK.search(stmt), (name, stmt[-160:])


def test_answer_is_two_ordered_segments(two_builds, monkeypatch):
    """The behaviour, on both builds: the catalogue in (price, id) order, then
    exactly the owned achievement rows in (price, id) order; and the two builds
    answer the same order although build B's equal-price rows were rewritten."""
    a, b = two_builds
    assert _relayout(b) > 0, "no shop price is shared; nothing to order"
    owned = {r["id"] for r in a.fetch(
        "SELECT pi.item_id AS id FROM player_items pi JOIN players p ON p.id = pi.player_id "
        "JOIN shop_items s ON s.id = pi.item_id WHERE p.steam_id = $1 AND s.rotation_pool = 'achievement'", ME)}
    assert len(owned) == OWNED_ACHIEVEMENTS, owned
    got_a, _ = _answers(a, monkeypatch)
    got_b, _ = _answers(b, monkeypatch)
    for url in (URL_ANON, URL_ME):
        rows = got_a[url]
        assert rows == got_b[url], (url, [(x, y) for x, y in zip(rows, got_b[url]) if x != y][:6])
        tail = OWNED_ACHIEVEMENTS if url == URL_ME else 0
        catalogue, appended = rows[:len(rows) - tail], rows[len(rows) - tail:]
        assert {i for i, _ in appended} == (owned if tail else set()), (url, appended)
        assert not owned & {i for i, _ in catalogue}, url
        for name, seg in (("catalogue", catalogue), ("achievement", appended)):
            keys = [(p, i) for i, p in seg]
            assert keys == sorted(keys), (url, name, keys[:8])                     # (price, id)
        assert len({p for _, p in catalogue}) < len(catalogue), url               # ties exist to be ordered
    # the appended owned rows share one price, so their order is the tiebreak's alone
    assert len({p for _, p in got_a[URL_ME][-OWNED_ACHIEVEMENTS:]}) == 1
