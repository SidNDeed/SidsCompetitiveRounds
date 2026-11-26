"""ALT-BAN-1 step 6: the costs of the list's fill and of the links route,
measured at 270000 marker rows with one address code shared by 200
accounts (ORDER-ALT-BAN-1-TURN2 step 6). Each read the two routes run on the
lane's tables is planned again with EXPLAIN (ANALYZE, BUFFERS) over the
same text and values; the plans are written to SCR_ALT_BAN_PLANS_DIR when
it is set. Bars: the list's call within 250 ms, the links route's within
500 ms (the best of three calls after one warm call), and each plan's own
execution time within the same bar; a measure over a bar makes the case
red with the numbers (ANSWER-ALT-BAN-T2: the bars stand).

Every id, mark and region is invented."""
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for p in (API, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from sqlalchemy import event, text  # noqa: E402

import main  # noqa: E402
import alt_signals as A  # noqa: E402
import test_ban_record_pg as BR  # noqa: E402
import test_alt_signals_record_pg as R  # noqa: E402
from inv_pg import case  # noqa: E402
import test_alt_ban_links_pg as L  # noqa: E402

MARKERS = 270000
SHARED_BY = 200
DAYS = 30
BANNED = 50
LIST_BAR_MS = 250.0
LINKS_BAR_MS = 500.0
LANE_TABLES = ("conn_markers", "ban_regions", "steam_family_shares", "ban_link_notices")

# Filler: accounts on codes of their own (one per account and day); the hot
# code: SHARED_BY accounts on every one of DAYS days; the banned accounts:
# one on the hot code, the rest on their own codes, every one with regions.
FILL_SQL = (
    "INSERT INTO conn_markers (steam_id, day, key_id, addr_mark, block_mark, family, conn_class, first_at, last_at)"
    " SELECT CAST($1::bigint + a AS text), CAST((now() AT TIME ZONE 'UTC') AS date) - d, $2,"
    " decode(md5('fa' || a || '-' || d) || md5('fb' || a || '-' || d), 'hex'),"
    " decode(md5('fk' || (a / 16)) || md5('fl' || (a / 16)), 'hex'), 4, 'none',"
    " now() - make_interval(days => d), now() - make_interval(days => d)"
    " FROM generate_series(1, $3::int) a, generate_series(0, $4::int - 1) d")


def _ms(t0):
    return (time.perf_counter() - t0) * 1000.0


async def _cost_world(env, admin):
    """The order's distribution: BANNED banned accounts (the first one of the
    SHARED_BY accounts on the hot code), the filler, the regions, two family
    shares; the tables analysed. Returns (hot, banned)."""
    kid = A.loaded_key().key_id
    hot = [await env.player("Cost Hot %03d" % i) for i in range(SHARED_BY)]
    banned = []
    for i in range(BANNED):
        p = hot[0] if i == 0 else await env.player("Cost Banned %02d" % i)
        await L._ban_row(env, admin, p.sid)
        banned.append(p)
    fill = (MARKERS - SHARED_BY * DAYS) // DAYS
    await env.conn.execute(FILL_SQL, 76561190090000000, kid, fill, DAYS)
    await env.conn.execute(
        "INSERT INTO conn_markers (steam_id, day, key_id, addr_mark, block_mark, family, conn_class,"
        " first_at, last_at) SELECT p, CAST((now() AT TIME ZONE 'UTC') AS date) - d, $2, $3, $4, 4, 'none',"
        " now() - make_interval(days => d), now() - make_interval(days => d)"
        " FROM unnest(CAST($1 AS text[])) p, generate_series(0, $5::int - 1) d",
        [h.sid for h in hot], kid, L._m("cost-hot"), L._m("cost-hot-blk"), DAYS)
    for i, p in enumerate(banned):
        for j, region in enumerate(("Ardenmark", "Vellshire", "Brynmoor")):
            await L._region(env, p.sid, "%s %d" % (region, i), hours_ago=j + 1)
        if i:
            await L._marker(env, p.sid, "cost-own-%d" % i, "cost-own-blk-%d" % i, 1)
    await L._share(env, banned[1].sid, L._account(hot[5].sid), 2)
    await L._share(env, hot[7].sid, L._account(banned[0].sid), 2)
    total = await env.conn.fetchval("SELECT count(*) FROM conn_markers")
    assert MARKERS <= total <= MARKERS + BANNED + 10, total
    for t in LANE_TABLES + ("player_bans", "players"):
        await env.conn.execute("ANALYZE %s" % t)
    return hot, banned


def test_the_list_and_the_links_route_within_their_bars(monkeypatch):
    out = {"plans": []}

    async def body(env):
        BR._open(env)
        L._keyed(env)
        await L._notice(env)
        admin = await BR._admin(env)
        async with BR._client(env) as c:
            hot, banned = await _cost_world(env, admin)
            seen = []

            def listen(conn, cursor, statement, parameters, context, executemany):
                if any(t in statement for t in LANE_TABLES):
                    seen.append((statement, parameters))
            calls = {}
            for name, call, bar in (
                    ("list", lambda: BR._list(c, admin), LIST_BAR_MS),
                    ("links", lambda: L._links(c, admin, hot[0].sid), LINKS_BAR_MS)):
                r = await call()
                assert r.status_code == 200, (name, r.status_code, r.text[:200])
                times = []
                for _n in range(3):
                    t0 = time.perf_counter()
                    r = await call()
                    times.append(_ms(t0))
                calls[name] = (min(times), statistics.median(times), bar, r.json())
                seen.clear()
                event.listen(env.engine.sync_engine, "before_cursor_execute", listen)
                try:
                    await call()
                finally:
                    event.remove(env.engine.sync_engine, "before_cursor_execute", listen)
                for statement, parameters in list(seen):
                    rows = await env.conn.fetch("EXPLAIN (ANALYZE, BUFFERS) " + statement, *parameters)
                    plan = "\n".join(r[0] for r in rows)
                    ex = [float(line.split("Execution Time:")[1].split("ms")[0]) for line in plan.splitlines()
                          if "Execution Time:" in line]
                    out["plans"].append((name, statement, plan, ex[0] if ex else None, bar))
            out["calls"] = calls
            out["hot"] = hot[0].sid
    try:
        case(monkeypatch, body, prefix="bancost")
    finally:
        A.install_key(None)
    where = os.environ.get("SCR_ALT_BAN_PLANS_DIR")
    lines = []
    for name, (best, median, bar, _a) in out["calls"].items():
        lines.append("CALL %s best %.1f ms median %.1f ms bar %.0f ms" % (name, best, median, bar))
    for name, statement, plan, ex, bar in out["plans"]:
        lines += ["", "PLAN %s execution %s ms (bar %.0f ms)" % (name, ex, bar), statement, plan]
    if where:
        os.makedirs(where, exist_ok=True)
        with open(os.path.join(where, "alt-ban-costs.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    print("\n".join(lines[:2]))
    links = out["calls"]["links"][3]
    assert any(e["how"] == "address" for e in links["links"]) and links["links_total"] == SHARED_BY, links
    assert len(links["links"]) == L.main._ALT_BAN_LINKS_SHOWN, len(links["links"])
    hot_row = next(e for e in out["calls"]["list"][3]["bans"] if e["steam_id"] == out["hot"])
    assert hot_row["links"] >= SHARED_BY - 1 and hot_row["regions"] == 3, hot_row
    assert len([p for p in out["plans"] if p[0] == "list"]) == 1, [p[1][:60] for p in out["plans"]]
    over = ["%s call %.1f ms > %.0f ms" % (name, best, bar) for name, (best, _m, bar, _a) in out["calls"].items()
            if best > bar]
    over += ["%s plan %s ms > %.0f ms: %s" % (name, ex, bar, statement[:60]) for name, statement, _p, ex, bar in out["plans"]
             if ex is None or ex > bar]
    # ANSWER-ALT-BAN-T2: the bars stand, and a miss is red.
    assert not over, over


# The two statements as they stood before the integrator's answer to
# QUESTION-ALT-BAN-T2 (candidate B: the relation statement's per-account
# CTEs materialized, so each is computed once before its joins; the list's
# block join an index probe per own block). Kept as the reference: on the
# cost distribution the new statements answer the same rows in the same
# order.
REF_RELATION_SQL = (
    'WITH s AS ( SELECT key_id, {mark} AS mark, day, conn_class FROM conn_markers WHERE steam_id ='
    ' CAST(:sid AS text) AND last_at >= now() - make_interval(days => CAST(:ow AS integer))), s_mark AS ('
    ' SELECT key_id, mark, max(day) AS s_last_day FROM s GROUP BY key_id, mark), s_day AS ( SELECT'
    ' DISTINCT key_id, mark, day FROM s), pop AS ( SELECT c.key_id, c.{mark} AS mark, count(DISTINCT'
    ' c.steam_id) AS n, count(DISTINCT c.steam_id) FILTER (WHERE c.steam_id <> CAST(:sid AS text)) AS'
    ' n_other FROM conn_markers c JOIN s_mark m ON m.key_id = c.key_id AND m.mark = c.{mark} WHERE'
    ' c.last_at >= now() - make_interval(days => CAST(:w AS integer)) GROUP BY c.key_id, c.{mark}), o AS'
    ' ( SELECT c.steam_id, c.key_id, c.{mark} AS mark, c.day, c.conn_class, (sd.day IS NOT NULL) AS'
    ' same_day FROM conn_markers c JOIN s_mark m ON m.key_id = c.key_id AND m.mark = c.{mark} JOIN'
    ' players p ON p.steam_id = c.steam_id AND p.deleted_at IS NULL LEFT JOIN s_day sd ON sd.key_id ='
    ' c.key_id AND sd.mark = c.{mark} AND sd.day = c.day WHERE c.steam_id <> CAST(:sid AS text) AND'
    ' c.last_at >= now() - make_interval(days => CAST(:w AS integer))), om AS ( SELECT o.steam_id,'
    ' o.key_id, o.mark, max(o.day) AS o_last_day, bool_or(o.same_day) AS any_same FROM o GROUP BY'
    ' o.steam_id, o.key_id, o.mark), per AS ( SELECT om.steam_id, count(*) AS shared_markers, count(*)'
    ' FILTER (WHERE NOT om.any_same) AS any_day_only, GREATEST(max(om.o_last_day), max(m.s_last_day)) AS'
    ' last_shared_day, min(pop.n) AS min_population, min(pop.n_other) - 1 AS others FROM om JOIN s_mark m'
    ' ON m.key_id = om.key_id AND m.mark = om.mark JOIN pop ON pop.key_id = om.key_id AND pop.mark ='
    ' om.mark GROUP BY om.steam_id), same AS ( SELECT o.steam_id, count(DISTINCT o.day) FILTER (WHERE'
    ' o.same_day) AS same_day_days, count(DISTINCT o.day) AS seen_days FROM o GROUP BY o.steam_id), cls'
    ' AS ( SELECT x.steam_id, array_agg(DISTINCT x.conn_class ORDER BY x.conn_class) AS classes FROM'
    ' (SELECT o.steam_id, o.conn_class FROM o UNION SELECT om.steam_id, s.conn_class FROM om JOIN s ON'
    ' s.key_id = om.key_id AND s.mark = om.mark) x GROUP BY x.steam_id) SELECT per.steam_id,'
    ' per.shared_markers, COALESCE(same.same_day_days, 0) AS same_day_days, per.any_day_only,'
    ' per.last_shared_day, per.min_population, cls.classes, count(*) OVER () AS total,'
    ' COALESCE(same.seen_days, 0) AS seen_days, per.others FROM per LEFT JOIN same ON same.steam_id ='
    ' per.steam_id JOIN cls ON cls.steam_id = per.steam_id ORDER BY COALESCE(same.same_day_days, 0) DESC,'
    ' per.min_population ASC, per.steam_id ASC LIMIT CAST(:cap AS integer)')


REF_LIST_SQL = (
    'WITH ids AS (SELECT u.sid, u.mark, u.ord FROM unnest(CAST(:ids AS text[]), CAST(:marks AS bytea[]))'
    ' WITH ORDINALITY AS u(sid, mark, ord)), rg AS (SELECT DISTINCT ON (r.steam_id) r.steam_id, r.region,'
    ' r.last_at FROM ban_regions r JOIN ids ON ids.sid = r.steam_id ORDER BY r.steam_id, r.last_at DESC,'
    ' r.region, r.conn_class), rn AS (SELECT r.steam_id, count(DISTINCT r.region) AS n FROM ban_regions r'
    ' JOIN ids ON ids.sid = r.steam_id GROUP BY r.steam_id), own AS (SELECT DISTINCT c.steam_id AS sid,'
    ' c.key_id, c.block_mark FROM conn_markers c JOIN ids ON ids.sid = c.steam_id WHERE c.last_at >='
    ' now() - make_interval(days => CAST(:ow AS integer))), nb AS (SELECT own.sid, o.steam_id AS other'
    ' FROM own JOIN conn_markers o ON o.key_id = own.key_id AND o.block_mark = own.block_mark WHERE'
    ' o.steam_id <> own.sid AND o.last_at >= now() - make_interval(days => CAST(:w AS integer))), sh AS'
    ' (SELECT m.steam_id AS sid, f.steam_id AS other FROM steam_family_shares m JOIN ids ON ids.sid ='
    ' m.steam_id JOIN steam_family_shares f ON f.key_id = m.key_id AND f.owner_mark = m.owner_mark WHERE'
    ' m.last_seen_at >= now() - make_interval(days => CAST(:ow AS integer)) AND f.steam_id <> m.steam_id'
    ' AND f.last_seen_at >= now() - make_interval(days => CAST(:w AS integer))), br AS (SELECT ids.sid,'
    ' f.steam_id AS other FROM ids JOIN steam_family_shares f ON f.key_id = CAST(:kid AS text) AND'
    ' f.owner_mark = ids.mark WHERE f.steam_id <> ids.sid AND f.last_seen_at >= now() -'
    ' make_interval(days => CAST(:w AS integer))), lk AS (SELECT u.sid, array_agg(DISTINCT u.other) AS'
    ' linked FROM ( SELECT sid, other FROM nb UNION SELECT sid, other FROM sh UNION SELECT sid, other'
    ' FROM br) u GROUP BY u.sid), fl AS'   # fix 1, H2: every linked account counted, as _BAN_LIST_ALT_SQL
    ' (SELECT m.steam_id AS sid, array_agg(DISTINCT m.owner_mark) AS marks FROM steam_family_shares m'
    ' JOIN ids ON ids.sid = m.steam_id WHERE m.key_id = CAST(:kid AS text) AND m.last_seen_at >= now() -'
    ' make_interval(days => CAST(:ow AS integer)) GROUP BY m.steam_id) SELECT ids.sid, rg.region,'
    ' rg.last_at AS region_at, COALESCE(rn.n, 0) AS regions, lk.linked, fl.marks, CASE WHEN ids.ord = 1'
    ' AND EXISTS (SELECT 1 FROM fl) THEN ARRAY(SELECT p.steam_id FROM players p WHERE p.deleted_at IS'
    ' NULL LIMIT CAST(:cap AS integer) + 1) END AS candidates FROM ids LEFT JOIN rg ON rg.steam_id ='
    ' ids.sid LEFT JOIN rn ON rn.steam_id = ids.sid LEFT JOIN lk ON lk.sid = ids.sid LEFT JOIN fl ON'
    ' fl.sid = ids.sid ORDER BY ids.ord')


def test_the_new_statements_answer_what_the_reference_statements_answered(monkeypatch):
    out = {}

    async def body(env):
        BR._open(env)
        L._keyed(env)
        await L._notice(env)
        admin = await BR._admin(env)
        hot, banned = await _cost_world(env, admin)
        key = A.loaded_key()
        ids = [p.sid for p in banned]
        page = {"ids": ids, "marks": [A.account_mark(key.secret, s) for s in ids], "kid": key.key_id,
                "ow": main._ALT_BAN_OWN_DAYS, "w": A.DUE_DAYS, "cap": A.OWNER_CANDIDATE_CAP}
        pairs = [("list", REF_LIST_SQL, main._BAN_LIST_ALT_SQL, page)]
        for sid in (hot[0].sid, hot[1].sid, hot[7].sid):
            rel = {"sid": sid, "w": A.DUE_DAYS, "ow": main._ALT_BAN_OWN_DAYS, "cap": main._ALT_BAN_LINKS_SHOWN}
            for mark in ("addr_mark", "block_mark"):
                pairs.append(("%s %s" % (mark, sid), REF_RELATION_SQL.replace("{mark}", mark),
                              main._alt_relation_sql(mark), rel))
        got = []
        async with env.sm() as db:
            for name, old, new, params in pairs:
                a = [tuple(r) for r in (await db.execute(text(old), params)).all()]
                b = [tuple(r) for r in (await db.execute(text(new), params)).all()]
                got.append((name, old != new, len(a), a == b))
            await db.rollback()
        out["got"] = got
    try:
        case(monkeypatch, body, prefix="bancost")
    finally:
        A.install_key(None)
    for name, changed, n, same in out["got"]:
        assert changed and n > 0 and same, (name, changed, n, same)
