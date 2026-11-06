"""Admin evidence report, phase 2 (ship-gate row B10): the evidence sections
through the four routes, live PostgreSQL.

The routes test's rig (a throwaway schema with the report's model tables and
the api's own app) gains the evidence tables, created by the statements of the
migrations that create them on the servers (242 runtime_settings; 370 card;
372 identity-clock; 390 combat), so the readers run against the production
column set, indexes and keys.

  P2-1  every report kind (game, series, pair, player): with the header, each
        seeded stored value is in its section at its seat; pair and player
        page 1 carry the window counts, contribution totals and 30-day totals.
  P2-2  without the header the body has no section key, equals the headed
        body with the section keys removed, and its audit row is the 1a one;
        with the header the audit row's schema is "2" and it carries the
        per-source state counts. The base commit's bot decodes the unheaded
        page of every route.
  P2-3  the unhandled cases on one page: no record, waiting, another match's
        row, conflict, purged, a switch off, parked; a statement that fails
        makes its source `unavailable`, the others answer, one audit row.
  P2-4  every section statement is typed, bounded and LATERAL-free (static),
        and on a distractor fixture each evidence-table statement plans an
        index scan, never a Seq Scan.

`ADMIN_EVIDENCE_TEST_PG_DSN` as in test_admin_evidence_routes_pg.
"""

import datetime as dt
import json
import os
import re
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import admin_evidence as ae  # noqa: E402
from test_admin_evidence_routes_pg import (AUDIT_KEYS, NOW, ROOT, _admin, _body,  # noqa: E402,F401
                                           rig)
from test_admin_evidence_sections import old_bot_ns  # noqa: E402

SQL_DIR = os.path.join(HERE, "..", "sql")
MIGRATIONS = ("242_runtime_settings.sql", "370_card_evidence.sql",
              "372_identity_clock_evidence.sql", "390_combat_evidence.sql")
EVIDENCE_TABLES = ("runtime_settings", "card_evidence", "card_games", "card_contrib",
                   "card_player_daily", "combat_evidence", "combat_games", "combat_contrib",
                   "combat_player_daily", "identity_clock_evidence", "identity_clock_games")
HEADER = {ae.SECTIONS_HEADER: ae.SECTIONS_PHASE}
_STMT = re.compile(
    r"(CREATE TABLE IF NOT EXISTS (?P<t>\w+) \(.*?\n\);"
    r"|CREATE (?:UNIQUE )?INDEX IF NOT EXISTS \w+\s+ON (?P<i>\w+)[^;]*;"
    r"|ALTER TABLE (?P<a>\w+) ADD COLUMN IF NOT EXISTS[^;]*;"
    r"|CREATE SEQUENCE IF NOT EXISTS \w+;)", re.S)


def evidence_ddl():
    """The evidence tables' CREATE TABLE, CREATE INDEX, ADD COLUMN and
    sequence statements, in migration order, comments removed."""
    out = []
    for name in MIGRATIONS:
        with open(os.path.join(SQL_DIR, name), encoding="utf-8") as fh:
            text = "\n".join(re.sub(r"--.*$", "", line) for line in fh.read().splitlines())
        for m in _STMT.finditer(text):
            table = m.group("t") or m.group("i") or m.group("a")
            if table is None or table in EVIDENCE_TABLES:
                out.append(m.group(0))
    created = {m.group("t") for s in out for m in _STMT.finditer(s) if m.group("t")}
    assert created == set(EVIDENCE_TABLES), sorted(set(EVIDENCE_TABLES) ^ created)
    return out


async def _up(rig):
    from sqlalchemy import text
    for stmt in evidence_ddl():
        await rig.conn.execute(text(stmt))
    await rig.conn.commit()


async def _ins(rig, table, row, jsonb=()):
    from sqlalchemy import text
    names = sorted(row)
    vals = ", ".join("CAST(:%s AS jsonb)" % n if n in jsonb else ":%s" % n for n in names)
    await rig.conn.execute(text("INSERT INTO %s (%s) VALUES (%s)"
                                % (table, ", ".join(names), vals)), row)


def _lohi(a, b):
    return tuple(sorted((a, b), key=str))


async def rec(rig, src, key, seat, other, room, **cols):
    row = {"stable_game_key": key, "attach_key": room, "seat_player_id": seat,
           "other_player_id": other, "payload": "{}", "payload_sha256": "0" * 64}
    if src == "card":
        row["deal_profile"] = cols.pop("deal_profile", "prof")
    row.update(cols)
    await _ins(rig, src + "_evidence", row, jsonb=("payload",))


async def grow(rig, src, key, a, b, match_id, **cols):
    lo, hi = _lohi(a, b)
    row = {"stable_game_key": key, "pair_lo": lo, "pair_hi": hi, "match_id": match_id}
    row.update(cols)
    await _ins(rig, src + "_games", row, jsonb=("record_faults",))


async def contrib(rig, src, key, a, b, subject, **cols):
    lo, hi = _lohi(a, b)
    row = {"stable_game_key": key, "pair_lo": lo, "pair_hi": hi,
           "subject_player_id": subject, "source": "self", "coverage": "one",
           "utc_day": NOW.date()}
    if src == "card":
        row.update({"recorder_player_id": subject, "deal_profile": "prof", "rules_rev": "r1"})
    row.update(cols)
    await _ins(rig, src + "_contrib", row, jsonb=("sums",))


async def setting(rig, key, value):
    await _ins(rig, "runtime_settings", {"key": key, "value": value})


async def get(rig, path, actor, headers=None):
    import httpx
    import main
    hdrs = {"X-Internal-Key": rig_key(), "X-Actor-Discord-Id": actor}
    hdrs.update(headers or {})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                 base_url="http://t") as c:
        r = await c.get(path, headers=hdrs)
    return r.status_code, r.content


def rig_key():
    import test_admin_evidence_routes_pg as rp
    return rp.KEY


def _strip(body):
    body = json.loads(json.dumps(body))
    body.pop("sections_summary", None)
    for g in body.get("games", []):
        g.pop("sections", None)
    return body


def _facts(facts):
    return dict(facts)


def _section(body, gi, src):
    return next(s for s in body["games"][gi]["sections"] if s["src"] == src)


async def _world(rig):
    """Two players with one ranked game in a series carrying every source's
    rows, the switches on (card's accept off), and daily rows for A."""
    await _up(rig)
    admin = await _admin(rig)
    a, sa, _d = await rig.player()
    b, sb, _d = await rig.player()
    s = await rig.series(a, b)
    g1 = await rig.match(a, b, NOW - dt.timedelta(hours=1), series=s,
                         photon_room_id="room-g1", is_ranked=True)
    for src in ae.SECTION_SOURCES:
        for w in ae.SECTION_SWITCHES:
            await setting(rig, "%s_evidence_%s" % (src, w),
                          "0" if (src, w) == ("card", "accept") else "1")
    await rec(rig, "card", "k1", a, b, "room-g1", pool_state="ok", deal_profile="prof-a")
    await rec(rig, "card", "k1", b, a, "room-g1", pool_state="collision",
              deal_profile="prof-b")
    await grow(rig, "card", "k1", a, b, g1, series_sc="1-0", processed_at=NOW,
               derive_fault="ValueError", parked_at=NOW)
    await contrib(rig, "card", "k1", a, b, a, hands=5, slots=12, obs_rare=2)
    await rec(rig, "combat", "k1", a, b, "room-g1", consts_version=3)
    await grow(rig, "combat", "k1", a, b, g1, coverage="one", records_n=1,
               record_faults='{"derive": 1}')
    await contrib(rig, "combat", "k1", a, b, a, sums='{"a1s": [1, 2, 3]}')
    await rec(rig, "identity_clock", "k1", b, a, "room-g1", post_clock="ok", post_proc="abc",
              post_sw_ms=10, post_unity_ms=11, post_photon_ts=12, conn_class="lan")
    await grow(rig, "identity_clock", "k1", a, b, g1, records_n=1, paired_points=4)
    await _ins(rig, "card_player_daily", {
        "subject_player_id": a, "day": NOW.date(), "source": "self", "coverage": "one",
        "deal_profile": "prof", "rules_rev": "r1", "games": 3, "hands": 9})
    await _ins(rig, "combat_player_daily", {
        "subject_player_id": a, "utc_day": NOW.date(), "source": "self", "coverage": "one",
        "games": 2, "sums": '{"a1s": [4, 4]}'}, jsonb=("sums",))
    await rig.commit()
    return admin, a, sa, b, sb, s, g1


def _paths(g1, s, sa, sb):
    return {"game": "%s/game/%s" % (ROOT, g1.hex),
            "series": "%s/series/%s" % (ROOT, s.hex),
            "pair": "%s/pair?a=%s&b=%s&games=1&page=2" % (ROOT, sa, sb),
            "player": "%s/player/%s?games=1&page=2" % (ROOT, sa),
            "pair1": "%s/pair?a=%s&b=%s&games=1" % (ROOT, sa, sb),
            "player1": "%s/player/%s?games=1" % (ROOT, sa)}


# ── P2-1 and P2-2: every report kind, with and without the header ──────────

def test_p2_every_report_kind_shows_the_stored_values_and_the_header_decides(rig):
    async def go():
        admin, a, sa, b, sb, s, g1 = await _world(rig)
        out = {}
        for shape, path in _paths(g1, s, sa, sb).items():
            before = len(await rig.audits())
            headed = await get(rig, path, admin, HEADER)
            plain = await get(rig, path, admin)
            out[shape] = (headed, plain, (await rig.audits())[before:])
        return out

    out = rig.run(go())
    old = old_bot_ns()
    for shape, ((hs, hc), (ps, pc), audits) in out.items():
        assert (hs, ps) == (200, 200), (shape, hc[:300], pc[:300])
        headed, plain = _body(hc), _body(pc)
        assert _strip(headed) == plain, shape
        assert "sections_summary" not in plain and all(
            "sections" not in g for g in plain["games"]), shape
        page, word = old["_aer_outcome"](200, plain)
        assert word is None and page is not None, (shape, word)
        assert len(audits) == 2, shape
        d2, d1 = audits[0]["details"], audits[1]["details"]
        d2 = json.loads(d2) if isinstance(d2, str) else d2
        d1 = json.loads(d1) if isinstance(d1, str) else d1
        assert d1["schema"] == "1a" and set(d1) == AUDIT_KEYS, shape
        assert d2["schema"] == "2" and set(d2) == AUDIT_KEYS | {"sections"}, shape
        if shape in ("pair1", "player1"):
            assert headed["games"] == [] and d2["sections"]["card"] == {
                "ok": 2 if shape == "pair1" else 1}
            continue
        assert d2["sections"] == {"card": {"ok": 1}, "combat": {"ok": 1},
                                  "identity_clock": {"ok": 1}}, shape
        card, combat, ice = (_section(headed, 0, src) for src in ae.SECTION_SOURCES)
        gf = _facts(card["game"])
        assert (gf["paired"], gf["accept"], gf["worker"]) == ("attached", "0", "1"), shape
        assert gf["derive_fault"] == "ValueError" and gf["parked_at"] is not None
        seat_of = {headed["subjects"][x["subject"]]["steam_id"]: x for x in card["seats"]}
        fa, fb = _facts(seat_of[sa]["facts"]), _facts(seat_of[sb]["facts"])
        assert (fa["pool_state"], fa["deal_profile"]) == ("ok", "prof-a"), shape
        assert (fb["pool_state"], fb["deal_profile"]) == ("collision", "prof-b"), shape
        assert (fa["contrib1.hands"], fa["contrib1.obs_rare"]) == ("5", "2")
        assert fb["contrib"] == "not_derived"
        cf = _facts(next(x for x in combat["seats"]
                         if headed["subjects"][x["subject"]]["steam_id"] == sa)["facts"])
        assert cf["consts_version"] == "3" and cf["contrib1.a1s.total"] == "6"
        assert _facts(combat["game"])["record_faults"] == "derive"
        isb = next(x for x in ice["seats"] if headed["subjects"][x["subject"]]["steam_id"] == sb)
        ib = _facts(isb["facts"])
        assert (ib["post_clock"], ib["post_proc"], ib["conn_class"]) == ("ok", "abc", "lan")
        assert _facts(ice["game"])["paired_points"] == "4"
    pair1 = _body(out["pair1"][0][1])
    entries = {(e["oi"], e["src"]): e for e in pair1["sections_summary"]}
    assert len(entries) == 6
    ca = _facts(entries[(0, "card")]["facts"])
    assert (ca["games"], ca["with_record"], ca["attached"]) == ("1", "1", "1")
    assert ca["self.hands"] == "5"
    assert _facts(entries[(0, "card")]["days30"])["self.hands"] == "9"
    assert _facts(entries[(0, "combat")]["days30"])["self.a1s.total"] == "8"
    assert _facts(entries[(1, "card")]["days30"])["daily"] == "not_derived"
    assert _facts(entries[(0, "identity_clock")]["facts"])["with_record"] == "0"
    assert _facts(entries[(1, "identity_clock")]["facts"])["post_clock.ok"] == "1"
    print("GATE p2-1/p2-2: six requests per header state, sections only with the header, "
          "unheaded body equal and decoded by the base bot, audit 1a and 2")


# ── P2-3: the unhandled cases ──────────────────────────────────────────────

def test_p2_unhandled_cases_are_words_and_the_page_answers(rig, monkeypatch):
    async def go():
        await _up(rig)
        admin = await _admin(rig)
        a, sa, _d = await rig.player()
        b, _sb, _d = await rig.player()
        t = NOW - dt.timedelta(hours=1)
        none = await rig.match(a, b, t, photon_room_id="room-none")
        wait = await rig.match(a, b, t - dt.timedelta(minutes=1), photon_room_id="room-w")
        other = await rig.match(a, b, t - dt.timedelta(minutes=2), photon_room_id="room-o")
        elsewhere = await rig.match(a, b, t - dt.timedelta(minutes=3), photon_room_id="room-e")
        mixed = await rig.match(a, b, t - dt.timedelta(minutes=4), photon_room_id="room-m")
        await rec(rig, "card", "kw", a, b, "room-w")
        await grow(rig, "card", "kw", a, b, None)
        await rec(rig, "combat", "ko", a, b, "room-o")
        await grow(rig, "combat", "ko", a, b, elsewhere)
        await rec(rig, "identity_clock", "km", a, b, "room-m", conflict_at=NOW,
                  conflict_kind="payload")
        await rec(rig, "identity_clock", "km", b, a, "room-m", lists_purged_at=NOW)
        await grow(rig, "identity_clock", "km", a, b, mixed)
        await setting(rig, "combat_evidence_worker", "0")
        await rig.commit()
        ids = (none, wait, other, mixed)
        pages = {}
        for gid in ids:
            st, c = await get(rig, "%s/game/%s" % (ROOT, gid.hex), admin, HEADER)
            pages[gid] = (st, _body(c))
        before = len(await rig.audits())
        broken = dict(ae.SECTION_SQL["combat"], records="SELECT no_such_column FROM nowhere")
        monkeypatch.setitem(ae.SECTION_SQL, "combat", broken)
        st, c = await get(rig, "%s/game/%s" % (ROOT, elsewhere.hex), admin, HEADER)
        audits = (await rig.audits())[before:]
        plain = await get(rig, "%s/game/%s" % (ROOT, elsewhere.hex), admin)
        return ids, pages, (st, _body(c)), audits, plain

    (none, wait, other, mixed), pages, failed, audits, plain = rig.run(go())
    assert all(st == 200 for st, _b in pages.values())
    body = pages[none][1]
    for src in ae.SECTION_SOURCES:
        s = _section(body, 0, src)
        assert s["state"] == "no_record" and [x["state"] for x in s["seats"]] == [
            "no_record", "no_record"], src
    assert _facts(_section(body, 0, "combat")["game"])["worker"] == "0"
    assert _facts(_section(body, 0, "card")["game"])["accept"] is None
    w = _section(pages[wait][1], 0, "card")
    assert w["state"] == "ok" and _facts(w["game"])["paired"] == "waiting"
    o = _section(pages[other][1], 0, "combat")
    assert o["state"] == "no_record" and _facts(o["game"])["other_game"] == "1"
    m = _section(pages[mixed][1], 0, "identity_clock")
    assert sorted(x["state"] for x in m["seats"]) == ["conflict", "purged"]
    assert any(_facts(x["facts"]).get("conflict_kind") == "payload" for x in m["seats"])
    st, fb = failed
    assert st == 200
    assert _section(fb, 0, "combat") == {"src": "combat", "state": "unavailable",
                                         "truncated": False, "game": [], "seats": []}
    assert _section(fb, 0, "card")["state"] == "no_record"
    assert _section(fb, 0, "identity_clock")["state"] == "no_record"
    assert len(audits) == 1
    d = audits[0]["details"]
    d = json.loads(d) if isinstance(d, str) else d
    assert d["sections"]["combat"] == {"unavailable": 1}
    assert plain[0] == 200 and _strip(fb) == _body(plain[1])
    print("GATE p2-3: no_record, waiting, other_game, conflict, purged, switch words; "
          "a failed statement is that source's unavailable and the page answers")


# ── P2-4: bounds and plans ─────────────────────────────────────────────────

def test_p2_every_section_statement_is_typed_bounded_and_lateral_free():
    seen = 0
    for src, stmts in ae.SECTION_SQL.items():
        for name, sql in stmts.items():
            seen += 1
            assert "LATERAL" not in sql.upper(), (src, name)
            binds = re.findall(r":(\w+)", sql)
            assert binds, (src, name)
            for bind in binds:
                assert re.search(r"CAST\(:%s AS [a-z]+(\[\])?\)" % bind, sql), (src, name, bind)
            assert sql.rstrip().endswith("LIMIT CAST(:n AS integer)"), (src, name)
            assert " WHERE " in sql, (src, name)
    assert seen == sum(len(v) for v in ae.SECTION_SQL.values()) and seen >= 15
    print("GATE p2-4 static: %d statements, every bind CAST, every one LIMITed, no LATERAL"
          % seen)


def _plan_nodes(plan):
    stack, out = [plan], []
    while stack:
        n = stack.pop()
        out.append(n)
        stack.extend(n.get("Plans", ()))
    return out


def test_p2_evidence_statements_plan_index_scans_on_a_distractor_fixture(rig):
    async def go():
        from sqlalchemy import text
        await _up(rig)
        players = [(await rig.player())[0] for _ in range(4)]
        a, b = players[0], players[1]
        for i in range(2500):
            x, y = players[2 + i % 2], players[3 - i % 2]
            key, room = "d%05d" % i, "room-d%05d" % i
            for src in ae.SECTION_SOURCES:
                await rec(rig, src, key, x, y, room)
                await grow(rig, src, key, x, y, uuid.uuid4())
            await contrib(rig, "card", key, x, y, x)
            await contrib(rig, "combat", key, x, y, x)
            await _ins(rig, "card_player_daily", {
                "subject_player_id": x, "day": NOW.date() - dt.timedelta(days=i),
                "source": "self", "coverage": "one", "deal_profile": "prof",
                "rules_rev": "r%d" % i})
            await _ins(rig, "combat_player_daily", {
                "subject_player_id": x, "utc_day": NOW.date() - dt.timedelta(days=i),
                "source": "self", "coverage": "one", "consts_version": i % 100})
        await rig.commit()
        for t in EVIDENCE_TABLES:
            await rig.conn.execute(text("ANALYZE %s" % t))
        await rig.conn.commit()
        params = {"rooms": ["room-x"], "pids": [str(a), str(b)], "ids": [str(uuid.uuid4())],
                  "keys": ["k-x"], "s": str(a), "d0": NOW.date() - dt.timedelta(days=29),
                  "n": 64}
        plans = {}
        for src, stmts in ae.SECTION_SQL.items():
            for name, sql in stmts.items():
                if name == "switches":
                    continue
                bind = {k: params[k] for k in set(re.findall(r":(\w+)", sql))}
                row = (await rig.conn.execute(text("EXPLAIN (FORMAT JSON) " + sql),
                                              bind)).scalar()
                plans[(src, name)] = row if not isinstance(row, str) else json.loads(row)
        await rig.conn.rollback()
        return plans

    plans = rig.run(go())
    assert len(plans) == sum(len(v) - 1 for v in ae.SECTION_SQL.values())
    for key, plan in plans.items():
        nodes = _plan_nodes(plan[0]["Plan"])
        scans = [n for n in nodes if n.get("Relation Name") in EVIDENCE_TABLES]
        assert scans, key
        assert not [n for n in scans if n["Node Type"] == "Seq Scan"], (key, [
            (n["Node Type"], n.get("Relation Name")) for n in scans])
    print("GATE p2-4 plans: %d evidence statements, index scans only, 2,500-game "
          "distractors per table" % len(plans))
