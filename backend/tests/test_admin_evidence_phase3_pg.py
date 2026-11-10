"""Admin evidence report, phase 3 (ship-gate row B10, ruling R5): stored
findings and the evidence ranks through the four routes, live PostgreSQL.

The phase-2 rig (test_admin_evidence_sections_pg) gains seat_evidence_findings,
created by the statements of the migrations that create it on the servers (368
the table; 370 its domain column and the unique index over it).

  P3-1  every report kind with both headers: the phase-2 body plus the
        findings (listed on the game whose stored match they name, as stored,
        rule ids synthetic) and, on page 1, the evidence block ranking the
        stored contributions and daily rows; removing the phase-3 additions
        gives the phase-2 body; the audit row's schema is "3".
  P3-2  deploy order: with the sections header alone, every route answers the
        bytes and audit row main's phase-2 code (the lane's base) builds from
        the same rows; main's code given both headers answers the same.
  P3-3  with no stored contribution anywhere the block says `not_derived`
        and carries no cell; the page answers.
  P3-4  on a distractor fixture each phase-3 statement plans on its named
        index, never a Seq Scan of an evidence table.

`ADMIN_EVIDENCE_TEST_PG_DSN` as in test_admin_evidence_routes_pg.
"""

import datetime as dt
import json
import os
import re
import subprocess
import sys
import types
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import admin_evidence as ae  # noqa: E402
import test_admin_evidence_sections_pg as p2  # noqa: E402
from test_admin_evidence_routes_pg import AUDIT_KEYS, NOW, ROOT, _admin, _body, rig  # noqa: E402,F401
from test_admin_evidence_phase3 import P2_BASE, _strip3  # noqa: E402
from test_admin_evidence_sections import REPO  # noqa: E402

HEADER = {ae.SECTIONS_HEADER: ae.SECTIONS_PHASE}
# literal, so the module collects on main (the negative control runs every
# test there); P3-1 asserts it equals the api's own words
HEADER3 = dict(HEADER, **{"X-Evidence-Phase": "3"})
_FINDINGS_STMT = re.compile(
    r"CREATE TABLE IF NOT EXISTS seat_evidence_findings \(.*?\n\);"
    r"|ALTER TABLE seat_evidence_findings\s+ADD COLUMN IF NOT EXISTS[^;]*;"
    r"|CREATE UNIQUE INDEX IF NOT EXISTS ux_seat_evidence_findings_domain\s+ON[^;]*;"
    r"|CREATE INDEX IF NOT EXISTS ix_seat_evidence_findings_game_match\s+ON[^;]*;", re.S)
MATCH_INDEX = "ix_seat_evidence_findings_game_match"


def findings_ddl():
    """seat_evidence_findings as 368 creates it, 370 extends it and 402
    indexes it by stored match (the partial index for scope 'game')."""
    out = []
    for name in ("368_seat_evidence.sql", "370_card_evidence.sql",
                 "402_seat_evidence_findings_match.sql"):
        with open(os.path.join(p2.SQL_DIR, name), encoding="utf-8") as fh:
            text = "\n".join(re.sub(r"--.*$", "", line) for line in fh.read().splitlines())
        out += [m.group(0) for m in _FINDINGS_STMT.finditer(text)]
    assert len(out) == 4, out
    return out


async def _up3(rig):
    from sqlalchemy import text
    for stmt in findings_ddl():
        await rig.conn.execute(text(stmt))
    await rig.conn.commit()


async def finding(rig, src, key, a, b, match_id, rule_id, flag_id=None):
    lo, hi = p2._lohi(a, b)
    row = {"scope": "game", "dedup_key": "%s%s|%s|%s" % (ae.FINDING_PREFIX[src], key, lo, hi),
           "rule_id": rule_id, "rules_rev": "zz-rev", "match_id": match_id,
           "details": '{"zz": 1}', "flag_id": flag_id,
           "domain": {"card": "card", "combat": "combat"}.get(src, "seat")}
    await p2._ins(rig, "seat_evidence_findings", row, jsonb=("details",))


async def _world3(rig):
    admin, a, sa, b, sb, s, g1 = await p2._world(rig)
    await _up3(rig)
    flag = uuid.uuid4()
    await finding(rig, "card", "k1", a, b, g1, "zz-c1", flag)
    await finding(rig, "card", "k1", a, b, None, "zz-c2")
    # B10-P3-R1 H1: no record, games row or contribution names this key; its
    # stored match is g1's, so g1 lists it
    await finding(rig, "card", "k-unnamed", a, b, g1, "zz-c3")
    await finding(rig, "combat", "k1", a, b, g1, "zz-x1")
    await finding(rig, "identity_clock", "k1", a, b, g1, "zz-i1")
    await rig.commit()
    return admin, a, sa, b, sb, s, g1, flag


def _details(row):
    d = row["details"]
    return json.loads(d) if isinstance(d, str) else d


# ── P3-1: every report kind with both headers ─────────────────────────────

def test_p3_every_report_kind_shows_findings_and_ranks_with_both_headers(rig):
    assert HEADER3 == dict(HEADER, **{ae.PHASE3_HEADER: ae.PHASE3_VALUE})

    async def go():
        admin, a, sa, b, sb, s, g1, flag = await _world3(rig)
        out = {}
        for shape, path in p2._paths(g1, s, sa, sb).items():
            before = len(await rig.audits())
            three = await p2.get(rig, path, admin, HEADER3)
            two = await p2.get(rig, path, admin, HEADER)
            out[shape] = (three, two, (await rig.audits())[before:])
        return out, sa, flag

    out, sa, flag = rig.run(go())
    for shape, ((ts, tc), (ws, wc), audits) in out.items():
        assert (ts, ws) == (200, 200), (shape, tc[:300], wc[:300])
        three, two = _body(tc), _body(wc)
        assert _strip3(three) == two, shape
        d3, d2 = _details(audits[0]), _details(audits[1])
        assert d2["schema"] == "2" and set(d2) == AUDIT_KEYS | {"sections"}, shape
        summary = shape in ("pair1", "player1")
        assert d3["schema"] == "3" and set(d3) == AUDIT_KEYS | {"sections", "findings"} | (
            {"evidence"} if summary else set()), shape
        if summary:
            ev = three["evidence"]
            assert ev["state"] == "ok" and ev["rows"] == 2 and d3["evidence"] == "ok", shape
            entries = {(e["oi"], e["src"]): dict(e["facts"]) for e in three["sections_summary"]}
            assert entries[(0, "card")]["findings"] == "2"
            assert entries[(0, "card")]["findings_unattributed"] == "1"
            keys = {c["ki"]: c["key"] for c in ev["catalog"]}
            cells = {(keys[c[0]], ev["strata"][c[1]]): c for c in ev["windows"][0]["cells"]}
            wmax = cells[("b4.rar.hands|SELF|seat|card_record|one|win_max.cell|profile", "prof")]
            assert (wmax[3], wmax[4], wmax[6]) == (1, 5.0, 1), wmax       # n, val, pop_n
            assert wmax[5] == pytest.approx(0.5)
            daily = cells[("b4.rar.hands|SELF|seat|card_daily|one|window|profile", "prof")]
            assert (daily[3], daily[4]) == (3, 9.0), daily
            xs = cells[("a1s.total|SELF|seat|combat_contrib|one|win_median.cell|consts", "0")]
            assert xs[4] == 6.0, xs
            if shape == "pair1":
                assert ev["windows"][1]["cells"] == [] or all(
                    keys[c[0]].split("|")[3] != "card_record" for c in ev["windows"][1]["cells"])
            continue
        assert d3["findings"] == {"card": 2, "combat": 1, "identity_clock": 1}, shape
        card, combat, ice = (p2._section(three, 0, src) for src in ae.SECTION_SOURCES)
        assert [r[0] for r in card["findings"]] == ["zz-c1", "zz-c3"], shape
        assert card["findings"][0][3] == str(flag) and card["findings"][1][3] is None
        assert card["findings"][0][1] == "game" and card["findings"][0][2] is not None
        assert dict(card["game"])["findings_unattributed"] == "1"
        assert [r[0] for r in combat["findings"]] == ["zz-x1"]
        assert [r[0] for r in ice["findings"]] == ["zz-i1"]
        assert "zz-rev" not in tc.decode("utf-8") and '"zz"' not in tc.decode("utf-8")
    print("GATE p3-1: six routes with both headers; findings as stored on their match, ranks "
          "on page 1, phase-2 body after removing them, audit schema 3")


# ── P3-2: deploy order against main's phase-2 construction ────────────────

def _p2_module():
    out = subprocess.run(["git", "-C", REPO, "show", P2_BASE + ":backend/api/admin_evidence.py"],
                         capture_output=True, timeout=60)
    if out.returncode:
        pytest.fail("the base api source is not readable here: %s"
                    % out.stderr.decode("utf-8", "replace")[:200])
    mod = types.ModuleType("admin_evidence_p2")
    mod.__file__ = os.path.join(HERE, "..", "api", "admin_evidence_p2.py")
    sys.modules[mod.__name__] = mod
    try:
        exec(compile(out.stdout.decode("utf-8"), mod.__file__, "exec"), mod.__dict__)
    finally:
        sys.modules.pop(mod.__name__, None)
    assert hasattr(mod, "SECTIONS_HEADER") and not hasattr(mod, "PHASE3_HEADER")
    return mod


def test_p3_phase2_pages_and_audit_rows_equal_main_s_construction(rig, monkeypatch):
    base = _p2_module()
    monkeypatch.setattr(base, "_CACHE", ae._CACHE)
    tip_serve = ae._aer_serve

    async def go():
        admin, _a, sa, _b, sb, s, g1, _flag = await _world3(rig)
        out = {}
        for shape, path in p2._paths(g1, s, sa, sb).items():
            n0 = len(await p2._audit_rows(rig))
            tip = await p2.get(rig, path, admin, HEADER)
            monkeypatch.setattr(ae, "_aer_serve", base._aer_serve)
            try:
                old = await p2.get(rig, path, admin, HEADER)
                old3 = await p2.get(rig, path, admin, HEADER3)
            finally:
                monkeypatch.setattr(ae, "_aer_serve", tip_serve)
            out[shape] = (tip, old, old3, (await p2._audit_rows(rig))[n0:])
        return out

    out = rig.run(go())
    for shape, ((ts, tc), (bs, bc), (b3s, b3c), rows) in out.items():
        assert (ts, bs, b3s) == (200, 200, 200), (shape, tc[:200], bc[:200])
        assert tc == bc == b3c, (shape, len(tc), len(bc), len(b3c))
        assert len(rows) == 3 and rows[0] == rows[1] == rows[2], (shape, rows)
        assert _details(rows[0])["schema"] == "2", shape
    print("GATE p3-2: %d routes with the sections header alone: bytes and audit rows equal "
          "main's phase-2 construction; main's code ignores the second header" % len(out))


# ── P3-3: nothing derived ─────────────────────────────────────────────────

def test_p3_no_stored_contribution_says_not_derived(rig):
    async def go():
        await p2._up(rig)
        await _up3(rig)
        admin = await _admin(rig)
        a, sa, _d = await rig.player()
        b, sb, _d = await rig.player()
        await rig.match(a, b, NOW - dt.timedelta(hours=2), photon_room_id="room-n")
        await rig.commit()
        out = {}
        for path in ("%s/player/%s?games=1" % (ROOT, sa),
                     "%s/pair?a=%s&b=%s&games=1" % (ROOT, sa, sb)):
            out[path] = await p2.get(rig, path, admin, HEADER3)
        return out

    for path, (status, content) in rig.run(go()).items():
        assert status == 200, (path, content[:300])
        ev = _body(content)["evidence"]
        assert ev["state"] == "not_derived" and ev["rows"] == 0 and ev["catalog"] == []
        assert all(w["cells"] == [] and w["more"] == 0 for w in ev["windows"])
        assert ev["census"] == ae.ev_census() and ev["fingerprint"] == ae.ev_fingerprint()
    print("GATE p3-3: no stored contribution: evidence not_derived, no cell, 200")


# ── B10-P3-R1: daily-only (L3), a repeat past the cap (H2), a cut daily
#    group (H3) ─────────────────────────────────────────────────────────────

def _cells(ev, wi=0):
    keys = {c["ki"]: c["key"] for c in ev["catalog"]}
    return {(keys[c[0]], ev["strata"][c[1]]): c for c in ev["windows"][wi]["cells"]}


DAILY_HANDS = ("b4.rar.hands|SELF|seat|card_daily|one|window|profile", "prof")


async def _daily(rig, subject, day, hands, games=1):
    await p2._ins(rig, "card_player_daily", {
        "subject_player_id": subject, "day": day, "source": "self", "coverage": "one",
        "deal_profile": "prof", "rules_rev": "r1", "games": games, "hands": hands})


def test_p3_daily_rows_alone_are_ok_with_daily_cells_only(rig):
    """L3: no stored contribution anywhere, a daily row for the account: the
    block is `ok`, reads 0 population rows and carries the daily cell only."""
    async def go():
        await p2._up(rig)
        await _up3(rig)
        admin = await _admin(rig)
        a, sa, _d = await rig.player()
        b, _sb, _d = await rig.player()
        await rig.match(a, b, NOW - dt.timedelta(hours=2), photon_room_id="room-d")
        await _daily(rig, a, NOW.date(), 4, games=2)
        await rig.commit()
        return await p2.get(rig, "%s/player/%s?games=1" % (ROOT, sa), admin, HEADER3)

    status, content = rig.run(go())
    assert status == 200, content[:300]
    ev = _body(content)["evidence"]
    assert ev["state"] == "ok" and ev["rows"] == 0 and ev["partial"] == 0
    cells = _cells(ev)
    assert all(k[0].split("|")[3] == "card_daily" for k in cells), sorted(cells)
    assert (cells[DAILY_HANDS][3], cells[DAILY_HANDS][4]) == (2, 4.0)
    print("GATE p3-l3: daily rows alone: ok, 0 population rows, daily cells only")


def test_p3_a_repeat_past_the_row_cap_refuses_and_its_control_is_ok(rig, monkeypatch):
    """H2: the row cap keeps only the newest contribution; two older eligible
    contributions share (match, subject, source, coverage, stratum) under two
    stable keys. The block is `unavailable`; without the second one, `ok`."""
    monkeypatch.setitem(ae.AER_CONTRACT_BOUNDS, "EV_POP_ROWS_MAX", 1)

    async def go(repeat):
        await p2._up(rig)
        await _up3(rig)
        admin = await _admin(rig)
        a, sa, _d = await rig.player()
        b, _sb, _d = await rig.player()
        new = await rig.match(a, b, NOW - dt.timedelta(hours=2), photon_room_id="room-n")
        old = await rig.match(a, b, NOW - dt.timedelta(hours=5), photon_room_id="room-o")
        await p2.contrib(rig, "card", "k-new", a, b, a, hands=3, match_id=new)
        await p2.contrib(rig, "card", "k-old1", a, b, a, hands=2, match_id=old)
        if repeat:
            await p2.contrib(rig, "card", "k-old2", a, b, a, hands=7, match_id=old)
        await rig.commit()
        return await p2.get(rig, "%s/player/%s?games=1" % (ROOT, sa), admin, HEADER3)

    seen = {}
    for repeat in (False, True):
        status, content = rig.run(go(repeat))
        assert status == 200, content[:300]
        seen[repeat] = _body(content)["evidence"]
    assert seen[True]["state"] == "unavailable" and seen[True]["windows"][0]["cells"] == []
    assert seen[False]["state"] == "ok" and seen[False]["truncated"] is True
    assert seen[False]["rows"] == 1
    print("GATE p3-h2: a repeat past the cap: unavailable; its control: ok, truncated")


def test_p3_a_daily_group_the_cap_cuts_is_left_out_never_summed_short(rig, monkeypatch):
    """H3: the account's two daily rows in one stratum, hands 1 (newest) and
    100. With room for both the cell is 101 over 2 games; with a cap of one
    row the group is left out whole and counted, never 1 over 1."""
    async def go(cap):
        monkeypatch.setitem(ae.AER_CONTRACT_BOUNDS, "EV_POP_ROWS_MAX", cap)
        await p2._up(rig)
        await _up3(rig)
        admin = await _admin(rig)
        a, sa, _d = await rig.player()
        b, _sb, _d = await rig.player()
        await rig.match(a, b, NOW - dt.timedelta(hours=2), photon_room_id="room-c")
        await _daily(rig, a, NOW.date(), 1)
        await _daily(rig, a, NOW.date() - dt.timedelta(days=1), 100)
        await rig.commit()
        return await p2.get(rig, "%s/player/%s?games=1" % (ROOT, sa), admin, HEADER3)

    seen = {}
    for cap in (2, 1):
        status, content = rig.run(go(cap))
        assert status == 200, content[:300]
        seen[cap] = _body(content)["evidence"]
    whole = _cells(seen[2])[DAILY_HANDS]
    assert (whole[3], whole[4]) == (2, 101.0), whole
    cut = seen[1]
    assert DAILY_HANDS not in _cells(cut) if cut["state"] == "ok" else cut["windows"][0]["cells"] == []
    assert cut["partial"] >= 1 and cut["truncated"] is True, cut
    print("GATE p3-h3: a daily group the cap cuts: left out and counted; whole: 101 over 2")


# ── P3-4: index plans and populated reads on a distractor fixture ─────────

_FINDINGS_DISTRACT = (
    "INSERT INTO seat_evidence_findings (scope, dedup_key, rule_id, rules_rev, domain, match_id) "
    "SELECT 'game', 'card d' || lpad(i::text, 5, '0') || '|x|y', 'zz-d', 'zz-rev', 'card', "
    "gen_random_uuid() FROM generate_series(0, CAST(:n AS integer) - 1) AS i")
# Old matches outside every window (40 days and more), cloned from one seeded
# row so every NOT NULL column carries the rig's own value.
_MATCHES_DISTRACT = (
    "INSERT INTO matches SELECT (jsonb_populate_record(m, jsonb_build_object("
    "'id', gen_random_uuid(), 'photon_room_id', NULL, "
    "'ended_at', now() - make_interval(days => 40 + i % 300, secs => i)))).* "
    "FROM matches m CROSS JOIN generate_series(0, CAST(:n AS integer) - 1) AS i "
    "WHERE m.id = CAST(:seed AS uuid)")


async def _l2_world(rig):
    """Eligible window games (ended 1, 2 and 3 hours ago) and excluded ones
    (invalidated, older than pop_days, inside the lag), each with a card and a
    combat contribution stored for it; DISTRACTORS old matches."""
    from sqlalchemy import text
    players = [(await rig.player())[0] for _ in range(4)]
    a, b = players[0], players[1]
    eligible, excluded = [], []
    for h in (1, 2, 3):
        eligible.append(await rig.match(a, b, NOW - dt.timedelta(hours=h),
                                        photon_room_id="room-e%d" % h))
    excluded.append(await rig.match(a, b, NOW - dt.timedelta(hours=4), photon_room_id="room-x1",
                                    invalidated_at=NOW))
    excluded.append(await rig.match(a, b, NOW - dt.timedelta(days=45), photon_room_id="room-x2"))
    excluded.append(await rig.match(a, b, dt.datetime.now(dt.timezone.utc)
                                    - dt.timedelta(seconds=5), photon_room_id="room-x3"))
    for i, mid in enumerate(eligible + excluded):
        await p2.contrib(rig, "card", "k-l2-%d" % i, a, b, a, hands=1 + i, match_id=mid)
        await p2.contrib(rig, "combat", "k-l2-%d" % i, a, b, a, sums='{"a1s": [1]}',
                         match_id=mid)
    await rig.conn.execute(text(_MATCHES_DISTRACT), {"n": p2.DISTRACTORS, "seed": str(excluded[1])})
    return players, eligible, excluded


def test_p3_statements_plan_on_their_named_indexes(rig):
    async def go():
        from sqlalchemy import text
        await p2._up(rig)
        await _up3(rig)
        players, eligible, excluded = await _l2_world(rig)
        await p2._distract(rig, players[2], players[3], p2.DISTRACTORS)
        await rig.conn.execute(text(_FINDINGS_DISTRACT), {"n": p2.DISTRACTORS})
        await rig.commit()
        for t in p2.EVIDENCE_TABLES + ("seat_evidence_findings", "matches"):
            await rig.conn.execute(text("ANALYZE %s" % t))
        await rig.conn.commit()
        params = {"keys": ["card k-x|a|b"], "n": 64, "pop_days": 30, "lag_s": 120,
                  "subjects": [str(players[0])], "d0": NOW.date() - dt.timedelta(days=29),
                  "ids": [str(uuid.uuid4())], "prefix": "card ", "s": str(players[0]),
                  "sources": sorted(ae.EV_PROV), "coverages": list(ae.EV_COVERAGES)}
        stmts = {("findings", "-"): ae.FINDINGS_SQL, ("by_match", "-"): ae.FINDINGS_MATCH_SQL}
        for src in ae.EV_SOURCES:
            stmts[("pop", src)] = ae.EV_POP_SQL[src]
            stmts[("dup", src)] = ae.EV_DUP_SQL[src]
            stmts[("daily", src)] = ae.EV_DAILY_SQL[src]
            stmts[("win", src)] = ae.EV_WIN_SQL[src]
            stmts[("windup", src)] = ae.EV_WIN_DUP_SQL[src]
        plans, got = {}, {}
        for name, sql in stmts.items():
            bind = {k: params[k] for k in set(re.findall(r":(\w+)", sql))}
            row = (await rig.conn.execute(text("EXPLAIN (FORMAT JSON) " + sql), bind)).scalar()
            plans[name] = row if not isinstance(row, str) else json.loads(row)
        for src in ae.EV_SOURCES:
            bind = {k: params[k] for k in set(re.findall(r":(\w+)", ae.EV_POP_SQL[src]))}
            got[src] = [str(r[0]) for r in (await rig.conn.execute(
                text(ae.EV_POP_SQL[src]), bind)).all()]
        await rig.conn.rollback()
        return plans, got, eligible

    plans, got, eligible = rig.run(go())
    # L2: the window reads exactly the eligible games' contributions, newest first
    want_ids = [str(m) for m in eligible]
    assert got == {src: want_ids for src in ae.EV_SOURCES}, got
    want = {("findings", "-"): {"seat_evidence_findings_once"},
            ("by_match", "-"): {MATCH_INDEX}}
    key_col = {"findings": "dedup_key", "by_match": "match_id", "pop": "match_id",
               "dup": "match_id", "daily": "subject_player_id", "win": "match_id",
               "windup": "match_id"}
    for src in ae.EV_SOURCES:
        spec = ae._SECTION_SPEC[src]
        want[("win", src)] = {"ix_%s_match" % spec["contrib"]}
        want[("windup", src)] = {"ix_%s_match" % spec["contrib"]}
        want[("pop", src)] = {"ix_%s_match" % spec["contrib"], "idx_matches_ended"}
        want[("dup", src)] = {"ix_%s_match" % spec["contrib"], "idx_matches_ended"}
        want[("daily", src)] = {"%s_pk" % spec["daily"]}
    evidence = set(p2.EVIDENCE_TABLES) | {"seat_evidence_findings", "matches"}
    for name, plan in plans.items():
        nodes = p2._plan_nodes(plan[0]["Plan"])
        scans = [n for n in nodes if n.get("Relation Name") in evidence]
        assert scans, name
        assert all(n["Node Type"] in p2.PERMITTED_SCANS for n in scans), (name, [
            (n["Node Type"], n.get("Relation Name"), n.get("Index Name")) for n in scans])
        # a Bitmap Index Scan names its index but no relation: it is read too
        probes = [n for n in nodes if n["Node Type"] == "Bitmap Index Scan"]
        named = {n["Index Name"]: n.get("Index Cond", "") for n in scans + probes
                 if "Index Name" in n}
        assert set(named) == want[name], (name, named)
        # each index is searched by its key column, not only a prefix or a filter
        for index, cond in named.items():
            col = "ended_at" if index == "idx_matches_ended" else key_col[name[0]]
            assert col in cond, (name, index, cond)
    print("GATE p3-4 plans: %d phase-3 statements on their named indexes, each searched by its "
          "key column; the window games by idx_matches_ended on ended_at; the population read "
          "returns the %d eligible games only, %d distractor rows" % (
              len(plans), len(eligible), p2.DISTRACTORS))


# ── B10-P3-R2 H1: the window cells' own complete read ─────────────────────

WIN_MAX = ("b4.rar.hands|SELF|seat|card_record|one|win_max.cell|profile", "prof")
# Card contributions under stable key `k1` whose stored pairs sort before any
# real pair (pair_lo 00000000-0000-0000-0000-...), on an old match of two other
# players: they fill the section's display read before the requested game's.
_SORT_FIRST = (
    "INSERT INTO card_contrib (stable_game_key, pair_lo, pair_hi, recorder_player_id, "
    "subject_player_id, source, coverage, deal_profile, rules_rev, utc_day, match_id, hands) "
    "SELECT 'k1', CAST('00000000-0000-0000-0000-' || lpad(to_hex(i), 12, '0') AS uuid), "
    "CAST('00000000-0000-0000-0001-000000000000' AS uuid), CAST(:a AS uuid), CAST(:a AS uuid), "
    "'self', 'one', 'prof', 'r1', CAST(:day AS date), CAST(:m AS uuid), 1 "
    "FROM generate_series(0, CAST(:n AS integer) - 1) AS i")


async def _sort_first(rig, subject):
    """SECTION_ROWS_MAX - 1 contributions about `subject` under `k1` that sort
    first in the section's display read, on a 45-day-old match of two other
    players."""
    from sqlalchemy import text
    c, _sc, _d = await rig.player()
    d, _sd, _d = await rig.player()
    old = await rig.match(c, d, NOW - dt.timedelta(days=45), photon_room_id="room-sf")
    await rig.conn.execute(text(_SORT_FIRST), {
        "a": str(subject), "m": str(old), "day": NOW.date(),
        "n": ae.AER_CONTRACT_BOUNDS["SECTION_ROWS_MAX"] - 1})


def test_r2_window_cells_read_every_covered_contribution_past_the_section_cap(rig):
    """R2-H1, the report's first scenario: the account's two covered games M1
    (k1, hands 1) and M2 (k2, hands 100) and 511 contributions under k1 that
    sort first. The section's display read stops at its cap of 512 before
    M2's row; the cells come from the window read and give 100 over 2, never
    1 over 1, with nothing cut or left out."""
    async def go():
        await p2._up(rig)
        await _up3(rig)
        admin = await _admin(rig)
        a, sa, _d = await rig.player()
        b, _sb, _d = await rig.player()
        m1 = await rig.match(a, b, NOW - dt.timedelta(hours=3), photon_room_id="room-w1")
        m2 = await rig.match(a, b, NOW - dt.timedelta(hours=2), photon_room_id="room-w2")
        await p2.contrib(rig, "card", "k1", a, b, a, hands=1, match_id=m1)
        await p2.contrib(rig, "card", "k2", a, b, a, hands=100, match_id=m2)
        await _sort_first(rig, a)
        await rig.commit()
        return await p2.get(rig, "%s/player/%s?games=2" % (ROOT, sa), admin, HEADER3)

    status, content = rig.run(go())
    assert status == 200, content[:300]
    body = _body(content)
    card = [e for e in body["sections_summary"] if e["src"] == "card"]
    assert card and all(e["truncated"] for e in card), card      # the display read was cut
    ev = body["evidence"]
    assert ev["state"] == "ok" and ev["truncated"] is False and ev["partial"] == 0, ev
    cell = _cells(ev)[WIN_MAX]
    assert (cell[3], cell[4]) == (2, 100.0), cell
    print("GATE p3-r2-1: past the section's display cap the window cell is 100 over 2")


def test_r2_a_window_repeat_on_an_old_game_refuses_and_its_control_is_ok(rig, monkeypatch):
    """R2-H1, the report's second scenario: the account's one covered game,
    older than the population window, with two facts under k1 and k2 for one
    (match, subject, source, coverage, stratum), and 511 contributions under
    k1 that sort first. The block is `unavailable` at the shipped caps and
    with a window cap of one row (where only the repeat check over the
    complete relation can see the second fact); without the second fact,
    `ok` with its one cell."""
    async def go(repeat, cap):
        if cap is not None:
            monkeypatch.setitem(ae.AER_CONTRACT_BOUNDS, "EV_POP_ROWS_MAX", cap)
        await p2._up(rig)
        await _up3(rig)
        admin = await _admin(rig)
        a, sa, _d = await rig.player()
        b, _sb, _d = await rig.player()
        g = await rig.match(a, b, NOW - dt.timedelta(days=40), photon_room_id="room-r2")
        await p2.contrib(rig, "card", "k1", a, b, a, hands=1, match_id=g)
        if repeat:
            await p2.contrib(rig, "card", "k2", a, b, a, hands=7, match_id=g)
        await _sort_first(rig, a)
        await rig.commit()
        return await p2.get(rig, "%s/player/%s?games=1" % (ROOT, sa), admin, HEADER3)

    seen = {}
    for repeat, cap in ((True, None), (True, 1), (False, 1)):
        status, content = rig.run(go(repeat, cap))
        assert status == 200, content[:300]
        seen[(repeat, cap)] = _body(content)["evidence"]
    for case in ((True, None), (True, 1)):
        assert seen[case]["state"] == "unavailable", (case, seen[case])
        assert seen[case]["windows"][0]["cells"] == [], case
    control = seen[(False, 1)]
    assert control["state"] == "ok" and control["partial"] == 0, control
    cell = _cells(control)[WIN_MAX]
    assert (cell[3], cell[4]) == (1, 1.0), cell
    print("GATE p3-r2-2: a window repeat on an old game: unavailable; its control: ok, 1 over 1")


def test_r2_a_window_stratum_the_cap_cuts_is_left_out_whole(rig, monkeypatch):
    """R2-H1, the window read's own cap: three covered games older than the
    population window, hands 1, 2 and 3 in one stratum. With room for the
    three rows the cell is 3 over 3; with a window cap of two rows the
    stratum is left out whole and counted, never 2 over 2."""
    async def go(cap):
        monkeypatch.setitem(ae.AER_CONTRACT_BOUNDS, "EV_POP_ROWS_MAX", cap)
        await p2._up(rig)
        await _up3(rig)
        admin = await _admin(rig)
        a, sa, _d = await rig.player()
        b, _sb, _d = await rig.player()
        for i in range(3):
            g = await rig.match(a, b, NOW - dt.timedelta(days=40 + i), photon_room_id="room-c%d" % i)
            await p2.contrib(rig, "card", "k-c%d" % i, a, b, a, hands=1 + i, match_id=g)
        await rig.commit()
        return await p2.get(rig, "%s/player/%s?games=3" % (ROOT, sa), admin, HEADER3)

    seen = {}
    for cap in (3, 2):
        status, content = rig.run(go(cap))
        assert status == 200, content[:300]
        seen[cap] = _body(content)["evidence"]
    whole = _cells(seen[3])[WIN_MAX]
    assert (whole[3], whole[4]) == (3, 3.0), whole
    cut = seen[2]
    assert cut["truncated"] is True and cut["partial"] >= 1, cut
    assert all(c == [] for c in [w["cells"] for w in cut["windows"]]) or WIN_MAX not in _cells(cut)
    print("GATE p3-r2-3: a window stratum the cap cuts: left out whole and counted; whole: 3 over 3")
