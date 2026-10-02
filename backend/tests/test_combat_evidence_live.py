"""Combat evidence against a real PostgreSQL 16: migration 369 applied twice,
rolled back and applied again (combat_evidence_pg); the combat route's
session rule, envelope answers, raw-first store, first-record rule, conflict
marker and hourly cap; the worker's combat pass with no revision (attach
only), under a SYNTHETIC revision in shadow and armed; the same stable key
under two seat pairs (M1); contributions counted once and re-rolled when a
one-sided game becomes paired; daily rows separated by measurement version
(M2); a derivation fault that keeps every record; the purge; the admin read.

One case schema per module run, on one event loop; each case uses its own
stable keys and synthetic 16-digit seats. Every rule value is synthetic,
built inside the test. Live cases FAIL rather than skip unless
SEAT_EVIDENCE_TEST_PG_OPTOUT=1 (seat_evidence_pg)."""

import asyncio
import hashlib
import json
import os
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import combat_evidence as ce  # noqa: E402
import combat_evidence_fixtures as fx  # noqa: E402
import combat_evidence_pg as cp  # noqa: E402
import combat_measures as cm  # noqa: E402
import main  # noqa: E402
import review_rules as rr  # noqa: E402
import review_testkit as tk  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402


def seat(n):
    """A synthetic 16-digit seat (no Steam account has 16 digits)."""
    return "10000000000007%02d" % n


ID_COMBAT = "r0000c001"


@pytest.fixture(scope="module")
def live():
    cp.require_live_pg()
    loop = asyncio.new_event_loop()
    ctx = cp.case("cev")
    c, sm, snaps = loop.run_until_complete(ctx.__aenter__())
    try:
        yield types.SimpleNamespace(run=loop.run_until_complete, case=c, sm=sm, snaps=snaps)
    finally:
        loop.run_until_complete(ctx.__aexit__(None, None, None))
        loop.close()


def _combat_doc(post=False, post_since=None):
    """synthetic_doc plus one synthetic combat rule over a public description
    (a visibly arbitrary value, chosen only to exercise the machinery)."""
    doc = tk.synthetic_doc()
    doc["rules"].append({
        "id": ID_COMBAT, "scope": "combat", "subject": "combat.cycle", "effect": "flag",
        "post": post, "post_since": post_since,
        "when": tk.cmp(tk.M("b2.cycle.rexp"), "gt", tk.V(777)),
        "show": [["units", "b2.cycle.units"], ["acct", "b2.cycle.account"]],
        "line": "synthetic combat {units} ({acct})"})
    return doc


def _cases():
    o, m = fx.a24_pair()
    return tk.quiet_cases() + [{"combat": fx.records(o, m), "fire": [ID_COMBAT]},
                               {"combat": fx.records(fx.empty_record(), None), "fire": []}]


@pytest.fixture(scope="module")
def revs(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("combat-review")
    store, shadow = tk.build_revision(tmp, _combat_doc(), _cases(), name="shadow")
    since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _s, armed = tk.build_revision(tmp, _combat_doc(True, since), _cases(), name="armed")

    def state(rev):
        rs = rr.load_dir(os.path.join(store, "rules-" + rev))
        return rr.State(rs.rev, rs)
    return types.SimpleNamespace(shadow=state(shadow), armed=state(armed))


@pytest.fixture
def signing(monkeypatch):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", fx.KEY)


class Req:
    def __init__(self, body, token=None, version="1.41.0"):
        self._b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.headers = {"X-Mod-Version": version}
        if token:
            self.headers["X-Session-Token"] = token
        self.client = None
        self.url = "http://combat-evidence.test/"
        self.state = types.SimpleNamespace()

    async def body(self):
        return self._b


async def _players(sm, *steams):
    ids = {}
    async with sm() as db:
        for s in steams:
            ids[s] = (await main.get_or_create_player(db, s, "Seat " + s[-3:])).id
        await db.commit()
    return ids


async def _session(sm, steam):
    token = "cev-" + uuid.uuid4().hex
    async with sm() as db:
        await db.execute(text(
            "INSERT INTO steam_sessions (steam_id, token_hash, verified, issued_at, expires_at) "
            "VALUES (:s, encode(sha256(convert_to(:t, 'UTF8')), 'hex'), true, now(), "
            "        now() + interval '1 hour')"), {"s": steam, "t": token})
        await db.commit()
    return token


async def _post(sm, body, token):
    async with sm() as db:
        r = await main.submit_combat_evidence(Req(body, token), db)
    if isinstance(r, dict):
        return 200, r
    return r.status_code, json.loads(r.body)


async def _scalar(sm, sql, **p):
    async with sm() as db:
        return (await db.execute(text(sql), p)).scalar()


async def _rows(sm, sql, **p):
    async with sm() as db:
        return (await db.execute(text(sql), p)).mappings().all()


async def _exec(sm, sql, **p):
    async with sm() as db:
        await db.execute(text(sql), p)
        await db.commit()


async def _set(sm, key, value):
    await _exec(sm, "INSERT INTO runtime_settings (key, value) VALUES (:k, :v) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", k=key, v=value)


async def _match(sm, ids, a, b, room, *, minutes_ago=10):
    vals = {"player1_id": ids[a], "player2_id": ids[b], "photon_room_id": room,
            "is_ranked": True, "p1_rounds_won": 5, "p2_rounds_won": 3,
            "winner_id": ids[a], "reported_by": ids[a]}
    async with sm() as db:
        row = await lh._insert(db, "matches", vals)
        await db.execute(text(
            "UPDATE matches SET ended_at = now() - make_interval(mins => CAST(:m AS int)), "
            "  created_at = now() - make_interval(mins => CAST(:m AS int)) WHERE id = :i"),
            {"m": minutes_ago, "i": row["id"]})
        await db.commit()
    return row["id"]


def _pair_bodies(a, b, stable, rounds=8, variant="base"):
    """(seat a's envelope as the owner, seat b's as the measuring seat)."""
    o, m = fx.a24_pair(variant)
    return (fx.envelope(o, seat=a, other=b, stable=stable, rounds=rounds),
            fx.envelope(m, seat=b, other=a, stable=stable, rounds=rounds))


def _errors(stats):
    return {k: v for k, v in stats.items() if str(k).startswith("error:")}


GAMES_SQL = ("SELECT pair_lo, pair_hi, match_id, attach_key, coverage, finalized_at, evaluated_rev, "
             "record_faults FROM combat_games WHERE stable_game_key = :k ORDER BY pair_lo")
FIND_SQL = ("SELECT rule_id, rules_rev, flag_id, details FROM seat_evidence_findings "
            "WHERE dedup_key LIKE :k ORDER BY rule_id")


# -- the migration ------------------------------------------------------------------------

def _no_time(snap):
    """runtime_settings without updated_at (a re-insert after the rollback
    takes a new timestamp by design)."""
    out = dict(snap)
    out["runtime_settings"] = [r[:2] for r in snap["runtime_settings"]]
    return out


def test_migration_369_twice_rollback_and_again(live):
    s = live.snaps
    assert s["first"] == s["again"]                                  # a re-run writes nothing
    for t in cp.CEV_TABLES:
        assert s["before"][t] is None and s["first"][t] == [] and s["rolled"][t] is None
    keys = {r[0] for r in s["first"]["runtime_settings"]}
    assert set(cp.CEV_SWITCHES) <= keys
    assert not set(cp.CEV_SWITCHES) & {r[0] for r in s["rolled"]["runtime_settings"]}
    assert s["rolled"] == s["before"]                                # the rollback moves nothing else
    assert _no_time(s["third"]) == _no_time(s["first"])              # and 369 reapplies whole
    on = {r[0]: r[1] for r in s["first"]["runtime_settings"]}
    assert all(on[k] == "1" for k in cp.CEV_SWITCHES)


# -- the route ----------------------------------------------------------------------------

def test_the_session_decides_first_then_the_switch_envelope_signature_and_record(live, signing):
    a, b, c = seat(1), seat(2), seat(3)

    async def go():
        sm = live.sm
        await _players(sm, a, b)
        ta, tb = await _session(sm, a), await _session(sm, b)
        good, _m = _pair_bodies(a, b, "ranked_cevr_000001")
        out = {}
        out["no_token_bad_body"] = await _post(sm, {"seat_steam_id": a}, None)
        out["other_seats_token"] = await _post(sm, good, tb)
        await _set(sm, "combat_evidence_accept", "0")
        out["off"] = await _post(sm, good, ta)
        await _set(sm, "combat_evidence_accept", "1")
        out["keys"] = await _post(sm, dict(good, extra=1), ta)
        bad_sig = dict(good, sig="0" * 64)
        out["sig"] = await _post(sm, bad_sig, ta)
        over = fx.envelope(fx.empty_record(), seat=a, other=b, stable="ranked_cevr_000002",
                           text="x" * (cm.RECORD_MAX_BYTES + 1))
        out["over"] = await _post(sm, over, ta)
        broken = fx.empty_record()
        broken["schema"] = 2
        out["record"] = await _post(sm, fx.envelope(broken, seat=a, other=b,
                                                    stable="ranked_cevr_000003",
                                                    text=json.dumps(broken)), ta)
        out["not_ready"] = await _post(sm, fx.envelope(fx.empty_record(), seat=a, other=c,
                                                       stable="ranked_cevr_000004"), ta)
        out["rows"] = await _scalar(sm, "SELECT count(*) FROM combat_evidence e JOIN players p "
                                        "ON p.id = e.seat_player_id WHERE p.steam_id = :s", s=a)
        out["players_c"] = await _scalar(sm, "SELECT count(*) FROM players WHERE steam_id = :s", s=c)
        return out
    out = live.run(go())
    assert out["no_token_bad_body"] == (401, {"detail": "seat_session"})
    assert out["other_seats_token"] == (401, {"detail": "seat_session"})
    assert out["off"] == (503, {"error": "combat_evidence_off"})
    assert out["keys"] == (400, {"detail": "envelope_keys"})
    assert out["sig"] == (403, {"detail": "signature"})
    assert out["over"] == (413, {"detail": "record_bytes"})
    assert out["record"][0] == 422
    assert out["not_ready"] == (409, {"status": "not_ready"})
    assert out["rows"] == 0 and out["players_c"] == 0               # nothing stored, no player made


def test_raw_first_store_first_record_rule_conflict_marker_and_hourly_cap(live, signing, monkeypatch):
    a, b, c = seat(4), seat(5), seat(6)

    async def go():
        sm = live.sm
        ids = await _players(sm, a, b, c)
        ta = await _session(sm, a)
        own, _m = _pair_bodies(a, b, "ranked_cevs_000001")
        out = {"first": await _post(sm, own, ta), "repeat": await _post(sm, own, ta)}
        out["row"] = (await _rows(sm, "SELECT payload, payload_sha256, payload_bytes, consts_version, "
                                      "header_mod_version, conflict_kind FROM combat_evidence "
                                      "WHERE stable_game_key = 'ranked_cevs_000001'"))[0]
        other = fx.envelope(fx.a24_pair()[0], seat=a, other=c, stable="ranked_cevs_000001")
        out["other_seat"] = await _post(sm, other, ta)
        changed = fx.envelope(fx.a24_pair("regen")[0], seat=a, other=b, stable="ranked_cevs_000001")
        out["payload"] = await _post(sm, changed, ta)
        out["marker"] = await _rows(sm, "SELECT conflict_kind, payload_sha256 FROM combat_evidence "
                                         "WHERE stable_game_key = 'ranked_cevs_000001'")
        monkeypatch.setattr(ce, "SEAT_HOURLY_CAP", 2)
        out["second_key"] = await _post(sm, fx.envelope(fx.empty_record(), seat=a, other=b,
                                                        stable="ranked_cevs_000002"), ta)
        out["capped"] = await _post(sm, fx.envelope(fx.empty_record(), seat=a, other=b,
                                                    stable="ranked_cevs_000003"), ta)
        out["ids"] = ids
        return out, own
    out, own = live.run(go())
    assert out["first"] == (200, {"status": "recorded"})
    assert out["repeat"] == (200, {"status": "already_recorded"})
    row = out["row"]
    raw = own["record"].encode("ascii")
    assert row["payload_sha256"] == hashlib.sha256(raw).hexdigest()   # stored as signed
    assert row["payload_bytes"] == len(raw)
    assert ce._jsonv(row["payload"]) == json.loads(own["record"])
    assert row["consts_version"] == 1 and row["header_mod_version"] == "1.41.0"
    assert row["conflict_kind"] is None
    assert out["other_seat"] == (409, {"status": "conflict"})
    assert out["payload"] == (409, {"status": "conflict"})
    (m,) = out["marker"]                                            # one row, first kept, marked once
    assert m["conflict_kind"] == "other_seat" and m["payload_sha256"] == row["payload_sha256"]
    assert out["second_key"] == (200, {"status": "recorded"})
    assert out["capped"][0] == 429 and out["capped"][1]["field"] == "seat_hourly_cap"


# -- the worker ---------------------------------------------------------------------------

def test_bar13_no_revision_attaches_and_derives_nothing(live, signing):
    a, b = seat(7), seat(8)
    key = "ranked_cevw_000001"

    async def go():
        sm = live.sm
        ids = await _players(sm, a, b)
        ta, tb = await _session(sm, a), await _session(sm, b)
        mid = await _match(sm, ids, a, b, key + "_r8")
        oa, mb = _pair_bodies(a, b, key)
        await _post(sm, oa, ta)
        await _post(sm, mb, tb)
        st = await ce.games_pass(sm, None)
        games = await _rows(sm, GAMES_SQL, k=key)
        n = {t: await _scalar(sm, "SELECT count(*) FROM %s WHERE subject_player_id = ANY(CAST(:i AS uuid[]))"
                              % t, i=[str(ids[a]), str(ids[b])])
             for t in ("combat_contrib", "combat_player_daily")}
        f = await _rows(sm, FIND_SQL, k=ce.DEDUP_PREFIX + key + "|%")
        return st, games, n, f, mid
    st, games, n, f, mid = live.run(go())
    assert not _errors(st) and st["evaluated"] == 0
    (g,) = games
    assert g["match_id"] == mid and g["attach_key"] == key + "_r8"
    assert g["evaluated_rev"] is None and g["finalized_at"] is None
    assert n == {"combat_contrib": 0, "combat_player_daily": 0} and f == []


def test_bar12_shadow_then_armed_and_bar11_counted_once_then_paired(live, signing, revs):
    a, b = seat(9), seat(10)
    key = "ranked_cevw_000002"

    async def go():
        sm = live.sm
        ids = await _players(sm, a, b)
        ta, tb = await _session(sm, a), await _session(sm, b)
        mid = await _match(sm, ids, a, b, key + "_r8")
        oa, mb = _pair_bodies(a, b, key)
        flags0 = await _scalar(sm, "SELECT count(*) FROM flagged_matches")
        await _post(sm, oa, ta)                                       # one side only
        s1 = await ce.games_pass(sm, revs.shadow)
        one = await _rows(sm, "SELECT subject_player_id, source, coverage, games FROM combat_player_daily "
                              "WHERE subject_player_id = ANY(CAST(:i AS uuid[])) ORDER BY 1, 2",
                          i=[str(ids[a]), str(ids[b])])
        g1 = await _rows(sm, GAMES_SQL, k=key)
        await _post(sm, mb, tb)                                       # the second record arrives
        s2 = await ce.games_pass(sm, revs.shadow)
        s3 = await ce.games_pass(sm, revs.shadow)                     # nothing changed: nothing re-derived
        two = await _rows(sm, "SELECT subject_player_id, source, coverage, games FROM combat_player_daily "
                              "WHERE subject_player_id = ANY(CAST(:i AS uuid[])) ORDER BY 1, 2",
                          i=[str(ids[a]), str(ids[b])])
        contrib = await _scalar(sm, "SELECT count(*) FROM combat_contrib WHERE stable_game_key = :k", k=key)
        f_shadow = await _rows(sm, FIND_SQL, k=ce.DEDUP_PREFIX + key + "|%")
        flags1 = await _scalar(sm, "SELECT count(*) FROM flagged_matches")
        s4 = await ce.games_pass(sm, revs.armed)
        f_armed = await _rows(sm, FIND_SQL, k=ce.DEDUP_PREFIX + key + "|%")
        flags = await _rows(sm, "SELECT match_id, flag_reason, auto_invalidated, flag_details "
                                "FROM flagged_matches WHERE match_id = :m", m=mid)
        g2 = await _rows(sm, GAMES_SQL, k=key)
        return (s1, s2, s3, s4), one, two, contrib, f_shadow, f_armed, flags, (flags0, flags1), g1, g2, ids
    stats, one, two, contrib, f_shadow, f_armed, flags, (flags0, flags1), g1, g2, ids = live.run(go())
    assert not any(_errors(s) for s in stats), stats
    # one-sided: evaluated, coverage one, not final (the second seat may still arrive)
    assert g1[0]["coverage"] == "one" and g1[0]["finalized_at"] is None
    assert {(r["source"], r["coverage"], r["games"]) for r in one} == {("self", "one", 1),
                                                                       ("meas", "one", 1)}
    # paired: the same game counted once, its coverage changed, not its count
    assert {(r["source"], r["coverage"], r["games"]) for r in two} == {
        ("self", "paired", 1), ("meas", "paired", 1)}
    assert len(two) == 4 and contrib == 4
    assert stats[2]["evaluated"] == 0
    # shadow: a finding carrying the rule id and revision, no flag
    assert [(f["rule_id"], f["rules_rev"], f["flag_id"]) for f in f_shadow] == [
        (ID_COMBAT, revs.shadow.ruleset.rev, None)]
    assert flags1 == flags0
    # armed: re-evaluated under the new revision, posted once, advisory
    assert g2[0]["evaluated_rev"] == revs.armed.ruleset.rev and g2[0]["finalized_at"] is not None
    assert f_armed[0]["rules_rev"] == revs.armed.ruleset.rev and f_armed[0]["flag_id"] is not None
    (flag,) = flags
    assert flag["flag_reason"] == "review" and flag["auto_invalidated"] is False
    det = ce._jsonv(flag["flag_details"])
    assert det["rule_id"] == ID_COMBAT and det["line"].startswith("synthetic combat ")


def test_m1_one_stable_key_under_two_seat_pairs_never_crosses(live, signing, revs):
    a, b, c, d = seat(11), seat(12), seat(13), seat(14)
    key = "ranked_cevw_000003"

    async def go():
        sm = live.sm
        ids = await _players(sm, a, b, c, d)
        tok = {s: await _session(sm, s) for s in (a, b, c, d)}
        m_ab = await _match(sm, ids, a, b, key + "_r8")
        m_cd = await _match(sm, ids, c, d, key + "_r7")
        for x, y, rounds in ((a, b, 8), (c, d, 7)):
            ox, my = _pair_bodies(x, y, key, rounds)
            await _post(sm, ox, tok[x])
            await _post(sm, my, tok[y])
        repair = await _post(sm, fx.envelope(fx.a24_pair()[0], seat=a, other=c, stable=key), tok[a])
        st = await ce.games_pass(sm, revs.shadow)
        games = await _rows(sm, GAMES_SQL, k=key)
        f = await _rows(sm, "SELECT dedup_key, match_id FROM seat_evidence_findings "
                            "WHERE dedup_key LIKE :k ORDER BY dedup_key", k=ce.DEDUP_PREFIX + key + "|%")
        return st, games, f, repair, ids, (m_ab, m_cd)
    st, games, f, repair, ids, (m_ab, m_cd) = live.run(go())
    assert not _errors(st)
    assert repair == (409, {"status": "conflict"})
    assert len(games) == 2
    by_match = {g["match_id"]: g for g in games}
    assert set(by_match) == {m_ab, m_cd}
    for mid, x, y, att in ((m_ab, a, b, key + "_r8"), (m_cd, c, d, key + "_r7")):
        g = by_match[mid]
        assert {g["pair_lo"], g["pair_hi"]} == {ids[x], ids[y]}
        assert g["attach_key"] == att and g["coverage"] == "paired"
        assert "other_attach_key" not in ce._jsonv(g["record_faults"])
    assert {r["match_id"] for r in f} == {m_ab, m_cd} and len(f) == 2


def test_m2_daily_rows_never_add_measurement_versions(live, signing, revs):
    a, b = seat(15), seat(16)

    async def go():
        sm = live.sm
        ids = await _players(sm, a, b)
        ta = await _session(sm, a)
        for key, consts in (("ranked_cevv_000001", 1), ("ranked_cevv_000002", 2)):
            await _match(sm, ids, a, b, key + "_r8")
            rec = fx.empty_record(consts)
            await _post(sm, fx.envelope(rec, seat=a, other=b, stable=key), ta)
        st = await ce.games_pass(sm, revs.shadow)
        rows = await _rows(sm, "SELECT source, coverage, consts_version, games FROM combat_player_daily "
                               "WHERE subject_player_id = :s ORDER BY consts_version", s=ids[a])
        return st, rows
    st, rows = live.run(go())
    assert not _errors(st)
    assert [(r["source"], r["consts_version"], r["games"]) for r in rows] == [("self", 1, 1),
                                                                          ("self", 2, 1)]


def test_a_derivation_fault_keeps_every_record_and_the_game_recovers(live, signing, revs, monkeypatch):
    a, b = seat(17), seat(18)
    key = "ranked_cevw_000004"

    def boom(rec, side):
        raise RuntimeError("planted")

    async def go():
        sm = live.sm
        ids = await _players(sm, a, b)
        ta, tb = await _session(sm, a), await _session(sm, b)
        await _match(sm, ids, a, b, key + "_r8")
        oa, mb = _pair_bodies(a, b, key)
        await _post(sm, oa, ta)
        await _post(sm, mb, tb)
        before = await _rows(sm, "SELECT id, payload_sha256 FROM combat_evidence WHERE stable_game_key = :k "
                                 "ORDER BY id", k=key)
        real = cm.rebuild_faults
        monkeypatch.setattr(cm, "rebuild_faults", boom)
        s1 = await ce.games_pass(sm, revs.shadow)
        g1 = await _rows(sm, GAMES_SQL, k=key)
        n1 = await _scalar(sm, "SELECT count(*) FROM combat_contrib WHERE stable_game_key = :k", k=key)
        f1 = await _rows(sm, FIND_SQL, k=ce.DEDUP_PREFIX + key + "|%")
        after = await _rows(sm, "SELECT id, payload_sha256 FROM combat_evidence WHERE stable_game_key = :k "
                                "ORDER BY id", k=key)
        monkeypatch.setattr(cm, "rebuild_faults", real)
        s2 = await ce.games_pass(sm, revs.shadow)
        g2 = await _rows(sm, GAMES_SQL, k=key)
        n2 = await _scalar(sm, "SELECT count(*) FROM combat_contrib WHERE stable_game_key = :k", k=key)
        return s1, g1, n1, f1, before, after, s2, g2, n2
    s1, g1, n1, f1, before, after, s2, g2, n2 = live.run(go())
    assert s1["rule_errors"] >= 1 and not _errors(s1)
    assert ce._jsonv(g1[0]["record_faults"])["derive"] == "RuntimeError"
    assert g1[0]["finalized_at"] is None and g1[0]["evaluated_rev"] is None
    assert n1 == 0 and f1 == [] and after == before and len(after) == 2
    assert not _errors(s2) and s2["rule_errors"] == 0
    assert "derive" not in ce._jsonv(g2[0]["record_faults"])
    assert g2[0]["finalized_at"] is not None and n2 == 4


# -- the purge and the admin read ---------------------------------------------------------

def test_the_admin_read_shows_the_display_case_and_a_purged_game_says_so(live, signing, revs):
    a, b, c, d = seat(19), seat(20), seat(21), seat(22)
    key, lone = "ranked_cevw_000005", "ranked_cevw_000006"

    async def go():
        sm = live.sm
        ids = await _players(sm, a, b, c, d)
        tok = {s: await _session(sm, s) for s in (a, b, c)}
        mid = await _match(sm, ids, a, b, key + "_r8")
        oa, mb = _pair_bodies(a, b, key, variant="regen")
        await _post(sm, oa, tok[a])
        await _post(sm, mb, tok[b])
        await _post(sm, fx.envelope(fx.a24_pair()[1], seat=c, other=d, stable=lone), tok[c])
        await ce.games_pass(sm, revs.shadow)
        async with sm() as db:
            paired = await ce.admin_view(db, match_id=str(mid), rs=revs.shadow.ruleset)
            single = await ce.admin_view(db, stable_game_key=lone, rs=revs.shadow.ruleset)
        await _exec(sm, "UPDATE combat_evidence SET received_at = now() - make_interval(days => CAST(:d AS int)) "
                        "WHERE stable_game_key = :k", d=ce.LIST_RETENTION_DAYS + 1, k=key)
        purged = await ce.purge_pass(sm)
        async with sm() as db:
            after = await ce.admin_view(db, stable_game_key=key, rs=revs.shadow.ruleset)
        kept = await _scalar(sm, "SELECT count(*) FROM combat_evidence WHERE stable_game_key = :k", k=key)
        return paired, single, purged, after, kept, mid
    paired, single, purged, after, kept, mid = live.run(go())
    (g,) = paired["games"]
    assert g["match_id"] == str(mid) and g["coverage"] == "paired" and len(g["records"]) == 2
    cases = {x["owner"]: x["case"] for x in g["display"]}
    assert set(cases.values()) <= {"both_agree", "both_differ"} and len(cases) == 2
    assert all(x["self_label"] == cm.LABEL_SELF or x["self_label"] is None for x in g["display"])
    assert [f["rule_id"] for f in g["findings"]] == [ID_COMBAT]
    (s,) = single["games"]
    assert s["match_id"] is None and len(s["records"]) == 1
    assert {x["owner"]: x["case"] for x in s["display"]} == {c: "only_owner", d: "only_measuring"}
    assert purged["lists"] >= 2 and kept == 2                         # lists go, the records stay
    (p,) = after["games"]
    assert p["view"] is None and p["display"][0]["not_run"] == {"lists_purged": 1}
    assert all(r["lists_purged"] for r in p["records"])


def test_exact_attach_identity_compares_only_records_of_the_attached_room(live, signing, revs):
    a, b = seat(23), seat(24)
    key = "ranked_cevw_000007"

    async def go():
        sm = live.sm
        ids = await _players(sm, a, b)
        ta, tb = await _session(sm, a), await _session(sm, b)
        mid = await _match(sm, ids, a, b, key + "_r8")
        oa, _mb = _pair_bodies(a, b, key, rounds=8)
        _oa, mb = _pair_bodies(a, b, key, rounds=7)                 # same key and pair, another room
        await _post(sm, oa, ta)
        await _post(sm, mb, tb)
        st = await ce.games_pass(sm, revs.shadow)
        g = await _rows(sm, GAMES_SQL, k=key)
        rec_ids = await _rows(sm, "SELECT id, attach_key FROM combat_evidence WHERE stable_game_key = :k "
                                  "ORDER BY id", k=key)
        daily = await _rows(sm, "SELECT source, coverage FROM combat_contrib WHERE stable_game_key = :k "
                                "ORDER BY source", k=key)
        return st, g, rec_ids, daily, mid
    st, g, rec_ids, daily, mid = live.run(go())
    assert not _errors(st)
    (game,) = g
    assert game["match_id"] == mid and game["attach_key"] == key + "_r8"
    assert game["coverage"] == "one" and game["finalized_at"] is None
    other = [r["id"] for r in rec_ids if r["attach_key"] == key + "_r7"]
    assert ce._jsonv(game["record_faults"])["other_attach_key"] == other and len(other) == 1
    assert [(r["source"], r["coverage"]) for r in daily] == [("meas", "one"), ("self", "one")]
