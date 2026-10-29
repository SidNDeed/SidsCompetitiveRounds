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
import seat_evidence as se  # noqa: E402
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


def test_m7_the_rollback_removes_exactly_the_combat_namespace_and_keeps_every_seat_row(live):
    """M-7: seat evidence findings in the legal key forms nearest the combat
    namespace (a seat stable key spelled `combat|...`, `combatX`, `combat_`,
    scope game and sitting) beside combat findings; the 369 rollback removes
    the combat rows only, every seat row stays byte for byte, and 369 then
    reapplies whole."""
    snaps = live.snaps
    lo, hi = cp._LO, cp._HI
    assert [d for _s, d, _r in cp.PLANTED_COMBAT] == [ce.dedup_key("X", lo, hi),
                                                       ce.dedup_key("ranked_k", lo, hi)]
    for _scope, dedup, _r in cp.PLANTED_SEAT:
        key = dedup.rsplit("|", 2)[0]
        assert se._KEY_CHARS.fullmatch(key), key          # a legal seat evidence key
        assert not dedup.startswith(ce.DEDUP_PREFIX)
    planted = {r[1] for r in snaps["planted"]["findings"]}
    kept = {r[1] for r in snaps["planted_rolled"]["findings"]}
    seat_rows = {d for _s, d, _r in cp.PLANTED_SEAT}
    combat_rows = {d for _s, d, _r in cp.PLANTED_COMBAT}
    assert seat_rows | combat_rows <= planted
    assert seat_rows <= kept and not (combat_rows & kept)
    before = [r for r in snaps["planted"]["findings"] if r[1] not in combat_rows]
    assert snaps["planted_rolled"]["findings"] == before                # nothing else moved
    for t in cp.CEV_TABLES:
        assert snaps["planted_rolled"][t] is None and snaps["fourth"][t] == []
    assert snaps["fourth"]["findings"] == snaps["planted_rolled"]["findings"]


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
    assert g["coverage"] == "paired"                                  # L-8: exact coverage kept
    assert ce._jsonv(g["record_faults"]) == {}                        # and nothing derived
    assert n == {"combat_contrib": 0, "combat_player_daily": 0} and f == []


def test_l8_no_revision_one_exact_record_is_coverage_one(live, signing):
    a, b = seat(41), seat(42)
    key = "ranked_cevw_000041"

    async def go():
        sm = live.sm
        ids = await _players(sm, a, b)
        ta, tb = await _session(sm, a), await _session(sm, b)
        await _match(sm, ids, a, b, key + "_r8")
        oa, _mb = _pair_bodies(a, b, key, rounds=8)
        _oa, mb = _pair_bodies(a, b, key, rounds=7)                 # the other seat, another room
        await _post(sm, oa, ta)
        await _post(sm, mb, tb)
        st = await ce.games_pass(sm, None)
        return st, await _rows(sm, GAMES_SQL, k=key)
    st, games = live.run(go())
    (g,) = games
    assert not _errors(st) and g["coverage"] == "one" and g["attach_key"] == key + "_r8"


async def _no_rev_game(sm, a, b, key, late_rounds):
    """Seat a's exact record, a no-revision pass, then seat b's record (of
    the attached room, or of another), another pass, and an idle pass."""
    ids = await _players(sm, a, b)
    ta, tb = await _session(sm, a), await _session(sm, b)
    await _match(sm, ids, a, b, key + "_r8")
    oa, _mb = _pair_bodies(a, b, key, rounds=8)
    _oa, mb = _pair_bodies(a, b, key, rounds=late_rounds)
    snaps = []
    sql = ("SELECT coverage, records_n, readiness_sig, processed_at, evaluated_rev, finalized_at, "
           "record_faults FROM combat_games WHERE stable_game_key = :k")
    await _post(sm, oa, ta)
    st1 = await ce.games_pass(sm, None)
    snaps.append((await _rows(sm, sql, k=key))[0])
    st_idle = await ce.games_pass(sm, None)                          # nothing new: not selected
    snaps.append((await _rows(sm, sql, k=key))[0])
    await _post(sm, mb, tb)
    st2 = await ce.games_pass(sm, None)
    snaps.append((await _rows(sm, sql, k=key))[0])
    n = {t: await _scalar(sm, "SELECT count(*) FROM %s WHERE subject_player_id = ANY(CAST(:i AS uuid[]))"
                          % t, i=[str(ids[a]), str(ids[b])])
         for t in ("combat_contrib", "combat_player_daily")}
    f = await _rows(sm, FIND_SQL, k=ce.DEDUP_PREFIX + key + "|%")
    return (st1, st_idle, st2), snaps, n, f


@pytest.mark.parametrize("late_rounds,cov", [(8, "paired"), (7, "one")], ids=["exact", "other_room"])
def test_f2_l8_no_revision_reselects_when_the_record_set_changes(live, signing, late_rounds, cov):
    a, b = (seat(57), seat(58)) if late_rounds == 8 else (seat(59), seat(60))
    key = "ranked_cevw_0000%d" % (57 if late_rounds == 8 else 59)
    sts, snaps, n, f = live.run(_no_rev_game(live.sm, a, b, key, late_rounds))
    assert not any(_errors(s) for s in sts)
    one, idle, late = snaps
    assert (one["coverage"], one["records_n"]) == ("one", 1) and one["readiness_sig"]
    assert idle["processed_at"] == one["processed_at"]                   # control: not reselected
    assert late["processed_at"] > one["processed_at"]                    # the late record reselects
    assert (late["coverage"], late["records_n"]) == (cov, 2)
    assert late["readiness_sig"] != one["readiness_sig"]
    for g in snaps:                                                      # and nothing is derived
        assert g["evaluated_rev"] is None and g["finalized_at"] is None
        assert ce._jsonv(g["record_faults"]) == {}
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
    for r in p["records"]:                                          # L-11: the allowlist
        rec = r["record"]
        for k in cm.LISTS:                                          # every raw list but cx_*
            assert (k in rec) == (k in ("cx_s", "cx_o")), k
        for k in cm.KEYS:                                           # every total and header kept
            assert k in rec or k in cm.LISTS, k
    assert set(ce.PURGED_LISTS) == set(cm.LISTS) - {"cx_s", "cx_o"}


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


def test_seat_route_a1_a_cut_game_record_with_end_is_recorded_not_refused(live, monkeypatch):
    """Seat evidence amendment A1 at the seat route: a record carrying `end`
    is stored (200 recorded), with `end` in the stored payload."""
    import seat_evidence_fixtures as sfx
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", sfx.KEY)
    a, b = seat(25), seat(26)

    def with_end(rec, kind):
        out = {}
        for k, v in rec.items():
            out[k] = v
            if k == "rounds":
                out["end"] = kind
        return out

    async def go():
        sm = live.sm
        await _players(sm, a, b)
        ta = await _session(sm, a)
        body = sfx.envelope(with_end(sfx.base_record(), "other_left"), seat=a, other=b,
                            stable="room_cev_a1_000001")
        async with sm() as db:
            r = await main.submit_seat_evidence(Req(body, ta), db)
        code, payload = (200, r) if isinstance(r, dict) else (r.status_code, json.loads(r.body))
        stored = await _scalar(sm, "SELECT payload ->> 'end' FROM seat_evidence "
                                   "WHERE stable_game_key = 'room_cev_a1_000001'")
        return code, payload, stored
    code, payload, stored = live.run(go())
    assert (code, payload) == (200, {"status": "recorded"})
    assert stored == "other_left"


# -- FIX PASS 1 ---------------------------------------------------------------------------

def test_m1_a_match_read_keeps_its_pair_under_a_shared_stable_key(live, signing, revs):
    """M-1, same key, two pairs: the read of match AB under stable key K
    shows AB's game only, never CD's records under the same key."""
    a, b, c, d = seat(43), seat(44), seat(45), seat(46)
    key = "ranked_cevw_000043"

    async def go():
        sm = live.sm
        ids = await _players(sm, a, b, c, d)
        tok = {s: await _session(sm, s) for s in (a, b, c, d)}
        m_ab = await _match(sm, ids, a, b, key + "_r8")
        await _match(sm, ids, c, d, key + "_r7")
        for x, y, rounds in ((a, b, 8), (c, d, 7)):
            ox, my = _pair_bodies(x, y, key, rounds)
            await _post(sm, ox, tok[x])
            await _post(sm, my, tok[y])
        await ce.games_pass(sm, revs.shadow)
        async with sm() as db:
            by_match = await ce.admin_view(db, match_id=str(m_ab), rs=revs.shadow.ruleset)
            by_key = await ce.admin_view(db, stable_game_key=key, rs=revs.shadow.ruleset)
        return by_match, by_key, m_ab
    by_match, by_key, m_ab = live.run(go())
    (g,) = by_match["games"]
    assert g["match_id"] == str(m_ab) and sorted(g["pair"]) == sorted([a, b])
    seats = {r["seat_steam_id"] for r in g["records"]} | {r["other_steam_id"] for r in g["records"]}
    assert seats == {a, b} and g["other_attachment"] == []
    assert {x["owner"] for x in g["display"]} == {a, b}
    assert len(by_key["games"]) == 2                                  # control: the key read has both


def test_m1_a_match_read_compares_only_its_attachment_and_names_the_other_room(live, signing, revs):
    """M-1, same pair, two rooms: only the record whose attach key IS the
    match's room is compared; the other room's record is provenance only.
    An unattached pair under two rooms is NOT-RUN, never compared."""
    a, b, c, d = seat(47), seat(48), seat(49), seat(50)
    key, loose = "ranked_cevw_000047", "ranked_cevw_000048"

    async def go():
        sm = live.sm
        ids = await _players(sm, a, b, c, d)
        tok = {s: await _session(sm, s) for s in (a, b, c, d)}
        mid = await _match(sm, ids, a, b, key + "_r8")
        oa, _mb = _pair_bodies(a, b, key, rounds=8)
        _oa, mb = _pair_bodies(a, b, key, rounds=7)
        await _post(sm, oa, tok[a])
        await _post(sm, mb, tok[b])
        oc, _md = _pair_bodies(c, d, loose, rounds=8)                 # no match: never attached
        _oc, md = _pair_bodies(c, d, loose, rounds=7)
        await _post(sm, oc, tok[c])
        await _post(sm, md, tok[d])
        await ce.games_pass(sm, revs.shadow)
        async with sm() as db:
            read = await ce.admin_view(db, match_id=str(mid), rs=revs.shadow.ruleset)
            unresolved = await ce.admin_view(db, stable_game_key=loose, rs=revs.shadow.ruleset)
        return read, unresolved
    read, unresolved = live.run(go())
    (g,) = read["games"]
    assert [r["attach_key"] for r in g["records"]] == [key + "_r8"]
    assert [(r["attach_key"], r["not_run"]) for r in g["other_attachment"]] == [
        (key + "_r7", "other_attachment")]
    cases = {x["owner"]: x["case"] for x in g["display"]}
    assert cases == {a: "only_owner", b: "only_measuring"}           # never a pair across rooms
    (u,) = unresolved["games"]
    assert u["view"] is None and u["view_not_run"] == "attachment_unresolved" and u["records"] == []
    assert u["display"][0]["not_run"] == {"attachment_unresolved": 1}
    assert sorted(r["not_run"] for r in u["other_attachment"]) == ["attachment_unresolved"] * 2


def test_m5_a_record_after_one_sided_finalization_reopens_and_replaces(live, signing, revs):
    """M-5: a game finalized one-sided (the second seat's record had not
    arrived within the expiry) is derived again when that record arrives:
    its contributions and daily rows become paired, counted once."""
    a, b = seat(51), seat(52)
    key = "ranked_cevw_000051"

    async def daily(sm, ids):
        return await _rows(sm, "SELECT subject_player_id, source, coverage, games FROM combat_player_daily "
                               "WHERE subject_player_id = ANY(CAST(:i AS uuid[])) ORDER BY 1, 2",
                           i=[str(ids[a]), str(ids[b])])

    async def go():
        sm = live.sm
        ids = await _players(sm, a, b)
        ta, tb = await _session(sm, a), await _session(sm, b)
        await _match(sm, ids, a, b, key + "_r8")
        oa, mb = _pair_bodies(a, b, key)
        await _post(sm, oa, ta)
        await ce.games_pass(sm, revs.shadow)
        await _exec(sm, "UPDATE combat_games SET first_seen_at = now() - make_interval(days => CAST(:d AS int)) "
                        "WHERE stable_game_key = :k", d=ce.GAME_EXPIRY_DAYS + 1, k=key)
        s_final = await ce.games_pass(sm, revs.shadow)
        g1 = await _rows(sm, GAMES_SQL + "", k=key)
        n1 = await _scalar(sm, "SELECT records_n FROM combat_games WHERE stable_game_key = :k", k=key)
        d1 = await daily(sm, ids)
        s_idle = await ce.games_pass(sm, revs.shadow)                 # control: nothing new, nothing redone
        await _post(sm, mb, tb)                                       # the late second record
        s_late = await ce.games_pass(sm, revs.shadow)
        g2 = await _rows(sm, GAMES_SQL, k=key)
        n2 = await _scalar(sm, "SELECT records_n FROM combat_games WHERE stable_game_key = :k", k=key)
        d2 = await daily(sm, ids)
        contrib = await _rows(sm, "SELECT source, coverage FROM combat_contrib WHERE stable_game_key = :k "
                                  "ORDER BY subject_player_id, source", k=key)
        s_after = await ce.games_pass(sm, revs.shadow)
        return s_final, g1, n1, d1, s_idle, s_late, g2, n2, d2, contrib, s_after
    s_final, g1, n1, d1, s_idle, s_late, g2, n2, d2, contrib, s_after = live.run(go())
    assert not any(_errors(s) for s in (s_final, s_idle, s_late, s_after))
    assert g1[0]["finalized_at"] is not None and g1[0]["coverage"] == "one" and n1 == 1
    assert {(r["source"], r["coverage"], r["games"]) for r in d1} == {("self", "one", 1),
                                                                      ("meas", "one", 1)}
    assert s_idle["evaluated"] == 0 and s_idle.get("final", 0) == 0
    assert s_late["evaluated"] >= 1
    assert g2[0]["finalized_at"] is not None and g2[0]["coverage"] == "paired" and n2 == 2
    assert {(r["source"], r["coverage"], r["games"]) for r in d2} == {("self", "paired", 1),
                                                                      ("meas", "paired", 1)}
    assert len(d2) == 4 and [r["coverage"] for r in contrib] == ["paired"] * 4
    assert s_after["evaluated"] == 0


def test_m7_combat_and_seat_findings_coexist_under_the_legal_collision_form(live, signing, revs):
    """M-7: seat evidence rows whose legal stable key is `combat|K` carry the
    dedup key the combat lane used to write for game K. The combat pass now
    writes, reads and stale-deletes only its own namespace: both seat rows
    (same rule id and another rule id) stay exactly as planted, and the admin
    read shows only the combat finding."""
    a, b = seat(53), seat(54)
    key = "ranked_cevw_000053"

    async def go():
        sm = live.sm
        ids = await _players(sm, a, b)
        ta, tb = await _session(sm, a), await _session(sm, b)
        mid = await _match(sm, ids, a, b, key + "_r8")
        lo, hi = sorted([ids[a], ids[b]], key=str)
        seat_key = "combat|" + key
        assert se._KEY_CHARS.fullmatch(seat_key)
        seat_dedup = "%s|%s|%s" % (seat_key, lo, hi)                 # the seat lane's own form
        for rule in (ID_COMBAT, "r0000s001"):
            await _exec(sm, "INSERT INTO seat_evidence_findings (scope, dedup_key, rule_id, rules_rev, "
                            "  details) VALUES ('game', :k, :r, 'r0000seat', CAST(:d AS jsonb))",
                        k=seat_dedup, r=rule, d=json.dumps({"lane": "seat"}))
        planted = await _rows(sm, "SELECT id, rule_id, rules_rev, details, changed_at FROM "
                                  "seat_evidence_findings WHERE dedup_key = :k ORDER BY id", k=seat_dedup)
        oa, mb = _pair_bodies(a, b, key)
        await _post(sm, oa, ta)
        await _post(sm, mb, tb)
        st = await ce.games_pass(sm, revs.shadow)
        after = await _rows(sm, "SELECT id, rule_id, rules_rev, details, changed_at FROM "
                                "seat_evidence_findings WHERE dedup_key = :k ORDER BY id", k=seat_dedup)
        combat = await _rows(sm, "SELECT dedup_key, rule_id, rules_rev FROM seat_evidence_findings "
                                 "WHERE dedup_key = :k", k=ce.dedup_key(key, lo, hi))
        async with sm() as db:
            read = await ce.admin_view(db, match_id=str(mid), rs=revs.shadow.ruleset)
        await _exec(sm, "DELETE FROM seat_evidence_findings WHERE dedup_key = :k", k=seat_dedup)
        return st, planted, after, combat, read, seat_dedup, lo, hi
    st, planted, after, combat, read, seat_dedup, lo, hi = live.run(go())
    assert not _errors(st)
    assert after == planted and len(after) == 2                        # untouched, both rules
    assert seat_dedup == "combat|%s|%s|%s" % (key, lo, hi)              # the old combat form
    assert [(r["rule_id"], r["rules_rev"]) for r in combat] == [(ID_COMBAT, revs.shadow.ruleset.rev)]
    assert combat[0]["dedup_key"].startswith(ce.DEDUP_PREFIX) and " " in combat[0]["dedup_key"]
    (g,) = read["games"]
    assert [(f["rule_id"], f["rules_rev"]) for f in g["findings"]] == [
        (ID_COMBAT, revs.shadow.ruleset.rev)]


def test_l9_deleting_a_player_removes_their_aggregate_rows_only(live):
    """L-9: both aggregate subject columns reference players(id) ON DELETE
    CASCADE: deleting a player removes that player's contributions and daily
    rows and no other player's."""
    a, b = seat(55), seat(56)

    async def go():
        sm = live.sm
        ids = await _players(sm, a, b)
        lo, hi = sorted([ids[a], ids[b]], key=str)
        for who in (a, b):
            await _exec(sm, "INSERT INTO combat_contrib (stable_game_key, pair_lo, pair_hi, "
                            "  subject_player_id, source, utc_day) "
                            "VALUES ('ranked_cevd_000001', :lo, :hi, :s, 'self', CURRENT_DATE)",
                        lo=lo, hi=hi, s=ids[who])
            await _exec(sm, "INSERT INTO combat_player_daily (subject_player_id, utc_day) "
                            "VALUES (:s, CURRENT_DATE)", s=ids[who])
        fk = await _rows(sm, "SELECT conrelid::regclass::text t, confdeltype::text confdeltype "
                             "FROM pg_constraint "
                             "WHERE contype = 'f' AND confrelid = 'players'::regclass "
                             "  AND conrelid::regclass::text IN ('combat_contrib', 'combat_player_daily') "
                             "ORDER BY 1")
        await _exec(sm, "DELETE FROM players WHERE id = :i", i=ids[a])
        left = {}
        for t in ("combat_contrib", "combat_player_daily"):
            left[t] = sorted(str(r["subject_player_id"]) for r in await _rows(
                sm, "SELECT subject_player_id FROM %s WHERE subject_player_id = ANY(CAST(:i AS uuid[]))" % t,
                i=[str(ids[a]), str(ids[b])]))
        return fk, left, ids
    fk, left, ids = live.run(go())
    assert [(r["t"], r["confdeltype"]) for r in fk] == [("combat_contrib", "c"),
                                                        ("combat_player_daily", "c")]
    assert left == {"combat_contrib": [str(ids[b])], "combat_player_daily": [str(ids[b])]}
