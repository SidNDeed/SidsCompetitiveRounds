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
HEADER3 = dict(HEADER, **{ae.PHASE3_HEADER: ae.PHASE3_VALUE})
_FINDINGS_STMT = re.compile(
    r"CREATE TABLE IF NOT EXISTS seat_evidence_findings \(.*?\n\);"
    r"|ALTER TABLE seat_evidence_findings\s+ADD COLUMN IF NOT EXISTS[^;]*;"
    r"|CREATE UNIQUE INDEX IF NOT EXISTS ux_seat_evidence_findings_domain\s+ON[^;]*;", re.S)


def findings_ddl():
    """seat_evidence_findings as 368 creates it and 370 extends it."""
    out = []
    for name in ("368_seat_evidence.sql", "370_card_evidence.sql"):
        with open(os.path.join(p2.SQL_DIR, name), encoding="utf-8") as fh:
            text = "\n".join(re.sub(r"--.*$", "", line) for line in fh.read().splitlines())
        out += [m.group(0) for m in _FINDINGS_STMT.finditer(text)]
    assert len(out) == 3, out
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
    await finding(rig, "combat", "k1", a, b, g1, "zz-x1")
    await finding(rig, "identity_clock", "k1", a, b, g1, "zz-i1")
    await rig.commit()
    return admin, a, sa, b, sb, s, g1, flag


def _details(row):
    d = row["details"]
    return json.loads(d) if isinstance(d, str) else d


# ── P3-1: every report kind with both headers ─────────────────────────────

def test_p3_every_report_kind_shows_findings_and_ranks_with_both_headers(rig):
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
            assert entries[(0, "card")]["findings"] == "1"
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
        assert d3["findings"] == {"card": 1, "combat": 1, "identity_clock": 1}, shape
        card, combat, ice = (p2._section(three, 0, src) for src in ae.SECTION_SOURCES)
        assert card["findings"][0][0] == "zz-c1" and card["findings"][0][3] == str(flag)
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


# ── P3-4: index plans on a distractor fixture ─────────────────────────────

_FINDINGS_DISTRACT = (
    "INSERT INTO seat_evidence_findings (scope, dedup_key, rule_id, rules_rev, domain) "
    "SELECT 'game', 'card d' || lpad(i::text, 5, '0') || '|x|y', 'zz-d', 'zz-rev', 'card' "
    "FROM generate_series(0, CAST(:n AS integer) - 1) AS i")


def test_p3_statements_plan_on_their_named_indexes(rig):
    async def go():
        from sqlalchemy import text
        await p2._up(rig)
        await _up3(rig)
        players = [(await rig.player())[0] for _ in range(4)]
        await p2._distract(rig, players[2], players[3], p2.DISTRACTORS)
        await rig.conn.execute(text(_FINDINGS_DISTRACT), {"n": p2.DISTRACTORS})
        await rig.commit()
        for t in p2.EVIDENCE_TABLES + ("seat_evidence_findings",):
            await rig.conn.execute(text("ANALYZE %s" % t))
        await rig.conn.commit()
        params = {"keys": ["card k-x|a|b"], "n": 64, "pop_days": 30, "lag_s": 120,
                  "subjects": [str(players[0])], "d0": NOW.date() - dt.timedelta(days=29)}
        stmts = {("findings", "-"): ae.FINDINGS_SQL}
        for src in ae.EV_SOURCES:
            stmts[("pop", src)] = ae.EV_POP_SQL[src]
            stmts[("daily", src)] = ae.EV_DAILY_SQL[src]
        plans = {}
        for name, sql in stmts.items():
            bind = {k: params[k] for k in set(re.findall(r":(\w+)", sql))}
            row = (await rig.conn.execute(text("EXPLAIN (FORMAT JSON) " + sql), bind)).scalar()
            plans[name] = row if not isinstance(row, str) else json.loads(row)
        await rig.conn.rollback()
        return plans

    plans = rig.run(go())
    want = {("findings", "-"): "seat_evidence_findings_once"}
    for src in ae.EV_SOURCES:
        spec = ae._SECTION_SPEC[src]
        want[("pop", src)] = "ix_%s_match" % spec["contrib"]
        want[("daily", src)] = "%s_pk" % spec["daily"]
    evidence = set(p2.EVIDENCE_TABLES) | {"seat_evidence_findings"}
    for name, plan in plans.items():
        nodes = p2._plan_nodes(plan[0]["Plan"])
        scans = [n for n in nodes if n.get("Relation Name") in evidence]
        assert scans, name
        assert all(n["Node Type"] in p2.PERMITTED_SCANS for n in scans), (name, [
            (n["Node Type"], n.get("Relation Name"), n.get("Index Name")) for n in scans])
        assert {n["Index Name"] for n in scans if "Index Name" in n} == {want[name]}, name
    print("GATE p3-4 plans: %d phase-3 statements on their named indexes, no Seq Scan of an "
          "evidence table, %d distractor rows" % (len(plans), p2.DISTRACTORS))
